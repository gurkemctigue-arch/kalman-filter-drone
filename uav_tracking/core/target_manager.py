"""Target selection, association, and lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import hypot, isfinite
from typing import Any, Hashable, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

import numpy as np

from .geometry import bbox_iou
from .kalman import ConstantVelocityKalman3D
from .estimator_strategies import ESTIMATOR_METHODS,make_state_estimator
from .models import Detection, TargetMode, TargetStatus, Track, TrackState


@dataclass(frozen=True)
class TargetUpdate:
    """Detailed result from one :meth:`TargetManager.update` call."""

    target: Optional[Track]
    status: TargetStatus
    tracks: Tuple[Track, ...]
    timestamp: Optional[float]
    switched: bool = False
    reacquired: bool = False
    # Indices refer to this acquisition's class-filtered detections, never
    # simulator identities. Ambiguous observations are intentionally unused.
    associations: Tuple[Tuple[int, int], ...] = ()
    ambiguous_track_ids: Tuple[int, ...] = ()
    ambiguous_detection_indices: Tuple[int, ...] = ()
    # Conservative merge evidence reserves observations without admitting
    # them through the strict measurement/association gates.
    merge_uncertainty_detection_indices: Tuple[int, ...] = ()


class TargetManager:
    """Manage tracks and a non-switching task target.

    ``AUTO_UNIQUE`` selects a target only when exactly one confirmed candidate
    exists, and pauses on every frame containing several candidates even
    after selection.  Only a unique return of the original track clears that
    ambiguity.  ``LOCKED_TARGET`` requires explicit initialization via
    :meth:`lock_target`, :meth:`lock_detection`, or the ``target_index``
    argument to :meth:`update`; it never silently switches to another track.
    """

    AUTO_UNIQUE = TargetMode.AUTO_UNIQUE
    LOCKED_TARGET = TargetMode.LOCKED_TARGET
    Mode = TargetMode

    def __init__(
        self,
        mode: TargetMode | str = TargetMode.AUTO_UNIQUE,
        *,
        target_class: Optional[Hashable] = None,
        min_hits: int = 2,
        max_coast_frames: int = 5,
        max_lost_frames: Optional[int] = None,
        max_coast_duration_s: Optional[float] = None,
        track_retention_duration_s: Optional[float] = None,
        association_iou_threshold: float = 0.01,
        association_max_distance: float = 2.0,
        association_mode: str = "legacy",
        reject_ambiguous_associations: bool = False,
        gate_threshold: float = 11.344866730144373,
        kf_kwargs: Optional[dict[str, Any]] = None,
        estimator_method: Optional[str] = None,
        ema_alpha: float = 0.35,
    ) -> None:
        self.mode = TargetMode(mode)
        self.target_class = target_class
        self.min_hits = int(min_hits)
        self.max_coast_frames = int(max_coast_frames)
        self.max_lost_frames = int(max_lost_frames if max_lost_frames is not None else max_coast_frames * 3)
        self.max_coast_duration_s = None if max_coast_duration_s is None else float(max_coast_duration_s)
        self.track_retention_duration_s = (
            None if track_retention_duration_s is None else float(track_retention_duration_s)
        )
        self.association_iou_threshold = float(association_iou_threshold)
        self.association_max_distance = float(association_max_distance)
        self.association_mode = str(association_mode).lower()
        self.reject_ambiguous_associations = bool(reject_ambiguous_associations)
        if self.association_mode not in {"legacy", "iou_2d", "hybrid_3d"}:
            raise ValueError("association_mode must be legacy, iou_2d, or hybrid_3d")
        self.gate_threshold = float(gate_threshold)
        if self.min_hits < 1:
            raise ValueError("min_hits must be at least one")
        if self.max_coast_frames < 0 or self.max_lost_frames < self.max_coast_frames:
            raise ValueError("max_lost_frames must be >= max_coast_frames >= 0")
        if self.max_coast_duration_s is not None:
            if not isfinite(self.max_coast_duration_s) or self.max_coast_duration_s <= 0.0:
                raise ValueError("max_coast_duration_s must be positive and finite")
            if self.track_retention_duration_s is None:
                self.track_retention_duration_s = 4.0 * self.max_coast_duration_s
            if (
                not isfinite(self.track_retention_duration_s)
                or self.track_retention_duration_s < self.max_coast_duration_s
            ):
                raise ValueError("track_retention_duration_s must be >= max_coast_duration_s")
        elif self.track_retention_duration_s is not None:
            raise ValueError("track_retention_duration_s requires max_coast_duration_s")
        if not 0.0 <= self.association_iou_threshold <= 1.0:
            raise ValueError("association_iou_threshold must be in [0, 1]")
        if self.association_max_distance <= 0.0 or not isfinite(self.association_max_distance):
            raise ValueError("association_max_distance must be positive and finite")
        self._kf_kwargs = dict(kf_kwargs or {})
        self.estimator_method=estimator_method
        self.ema_alpha=float(ema_alpha)
        if estimator_method is not None and estimator_method not in ESTIMATOR_METHODS:
            raise ValueError(f"estimator_method must be one of {ESTIMATOR_METHODS}")
        if not 0<self.ema_alpha<=1:
            raise ValueError("ema_alpha must be in (0,1]")
        self._tracks: dict[int, Track] = {}
        self._next_track_id = 1
        self._target_track_id: Optional[int] = None
        # Task identity is deliberately separate from the transient tracker
        # ID.  It is assigned when a task target is selected and survives
        # track reconstruction during short occlusions.
        self._target_uuid: Optional[str] = None
        self._pending_target_uuid: Optional[str] = None
        self._requires_reselection = False
        self._auto_unique_ambiguous = False
        self._locked_ambiguous = False
        self._ambiguous_track_ids: set[int] = set()
        self._ambiguous_detection_indices: set[int] = set()
        self._merge_uncertainty_detection_indices: set[int] = set()
        self._pending_target_index: Optional[int] = None
        self._pending_target_track_id: Optional[int] = None
        self._frame_index = 0
        self._timestamp: Optional[float] = None
        self._status = TargetStatus.UNINITIALIZED
        self._last_result = TargetUpdate(None, self._status, tuple(), None)

    @property
    def tracks(self) -> Tuple[Track, ...]:
        return tuple(self._tracks.values())

    @property
    def target(self) -> Optional[Track]:
        return self._tracks.get(self._target_track_id) if self._target_track_id is not None else None

    @property
    def current_target(self) -> Optional[Track]:
        return self.target

    @property
    def status(self) -> TargetStatus:
        return self._status

    @property
    def target_track_id(self) -> Optional[int]:
        return self._target_track_id

    @property
    def target_uuid(self) -> Optional[str]:
        return self._target_uuid

    @property
    def last_result(self) -> TargetUpdate:
        return self._last_result

    def reset(self) -> None:
        self._tracks.clear()
        self._next_track_id = 1
        self._target_track_id = None
        self._target_uuid = None
        self._pending_target_uuid = None
        self._requires_reselection = False
        self._auto_unique_ambiguous = False
        self._locked_ambiguous = False
        self._ambiguous_track_ids.clear()
        self._ambiguous_detection_indices.clear()
        self._merge_uncertainty_detection_indices.clear()
        self._pending_target_index = None
        self._pending_target_track_id = None
        self._frame_index = 0
        self._timestamp = None
        self._status = TargetStatus.UNINITIALIZED
        self._last_result = TargetUpdate(None, self._status, tuple(), None)

    def set_mode(self, mode: TargetMode | str, *, clear_target: bool = True) -> None:
        self.mode = TargetMode(mode)
        self._auto_unique_ambiguous = False
        self._locked_ambiguous = False
        if clear_target:
            self._target_track_id = None
            self._target_uuid = None
            self._pending_target_uuid = None
            self._requires_reselection = False
            self._status = TargetStatus.UNINITIALIZED

    def lock_target(self, track_id: int, *, target_uuid: Optional[str] = None) -> bool:
        """Lock an existing track ID; returns ``False`` if it is unavailable."""

        track_id = int(track_id)
        normalized_uuid = None if target_uuid is None or not str(target_uuid).strip() else str(target_uuid).strip()
        self.mode = TargetMode.LOCKED_TARGET
        self._auto_unique_ambiguous = False
        self._locked_ambiguous = False
        self._pending_target_index = None
        if track_id not in self._tracks or not self._tracks[track_id].is_active:
            self._pending_target_track_id = track_id
            self._pending_target_uuid = normalized_uuid
            return False
        self._requires_reselection = False
        self._target_track_id = track_id
        self._pending_target_track_id = None
        self._pending_target_uuid = None
        self._target_uuid = normalized_uuid or self._target_uuid or str(uuid4())
        self._status = TargetStatus.TRACKING if self._tracks[track_id]._matched_this_frame else TargetStatus.COASTING
        return True

    def lock_detection(self, detection_index: int, *, target_uuid: Optional[str] = None) -> None:
        """Select a detection in the next update as the locked target."""

        if int(detection_index) < 0:
            raise ValueError("detection_index must be non-negative")
        self.mode = TargetMode.LOCKED_TARGET
        self._auto_unique_ambiguous = False
        self._locked_ambiguous = False
        self._pending_target_index = int(detection_index)
        self._pending_target_track_id = None
        self._pending_target_uuid = None if target_uuid is None or not str(target_uuid).strip() else str(target_uuid).strip()
        self._target_track_id = None
        self._target_uuid = None
        self._requires_reselection = False
        self._status = TargetStatus.UNINITIALIZED

    def initialize_target(
        self,
        *,
        track_id: Optional[int] = None,
        detection_index: Optional[int] = None,
        target_uuid: Optional[str] = None,
    ) -> None:
        if (track_id is None) == (detection_index is None):
            raise ValueError("provide exactly one of track_id or detection_index")
        if track_id is not None:
            self.lock_target(track_id, target_uuid=target_uuid)
        else:
            self.lock_detection(int(detection_index), target_uuid=target_uuid)

    def unlock_target(self) -> None:
        self._target_track_id = None
        self._target_uuid = None
        self._pending_target_uuid = None
        self._pending_target_index = None
        self._pending_target_track_id = None
        self._requires_reselection = False
        self._auto_unique_ambiguous = False
        self._locked_ambiguous = False
        self._status = TargetStatus.UNINITIALIZED

    def _new_filter(self) -> ConstantVelocityKalman3D:
        kwargs = dict(self._kf_kwargs)
        kwargs.setdefault("gate_threshold", self.gate_threshold)
        if self.estimator_method is None:
            return ConstantVelocityKalman3D(**kwargs)
        return make_state_estimator(self.estimator_method,ema_alpha=self.ema_alpha,**kwargs)

    def _new_track(self, detection: Detection, *, timestamp: Optional[float] = None) -> Track:
        track_timestamp = detection.timestamp if timestamp is None else float(timestamp)
        track = Track(
            track_id=self._next_track_id,
            class_id=detection.class_id,
            bbox=detection.bbox,
            state=TrackState.TENTATIVE if self.min_hits > 1 else TrackState.CONFIRMED,
            confidence=detection.confidence,
            created_timestamp=track_timestamp,
            last_update_timestamp=track_timestamp,
            last_detection=detection,
        )
        self._next_track_id += 1
        track._filter = self._new_filter()
        # A newly created track is a measurement-backed candidate in the
        # current frame, so AUTO_UNIQUE and explicit first-frame locking can
        # consider it immediately.
        track._matched_this_frame = True
        if detection.position_3d is not None:
            track._filter.initialize(detection.position_3d, timestamp=track_timestamp)
            track.last_measurement_timestamp = track_timestamp
            self._copy_filter_to_track(track)
        self._tracks[track.track_id] = track
        return track

    @staticmethod
    def _position_of_detection(detection: Detection) -> Optional[np.ndarray]:
        return None if detection.position_3d is None else np.asarray(detection.position_3d, dtype=float)

    def _copy_filter_to_track(self, track: Track) -> None:
        if track._filter is None or not track._filter.initialized:
            return
        track.position_3d = tuple(float(value) for value in track._filter.position)
        track.velocity_3d = tuple(float(value) for value in track._filter.velocity)
        track.covariance_3d = track._filter.covariance[:3, :3].copy()
        track.covariance_6d = track._filter.covariance.copy()

    def _expire_by_time(self, track: Track, timestamp: Optional[float]) -> None:
        """Apply optional second-based lifecycle without advancing a filter.

        Three-dimensional prediction freshness is measured from the last
        accepted depth measurement; repeated 2-D boxes cannot reset it.
        """

        if track.state == TrackState.REMOVED or self.max_coast_duration_s is None or timestamp is None:
            return
        anchor = track.last_measurement_timestamp
        if anchor is None:
            anchor = track.created_timestamp
        age_s = max(0.0, float(timestamp) - float(anchor))
        if age_s > float(self.track_retention_duration_s):
            track.state = TrackState.REMOVED
        elif age_s > self.max_coast_duration_s:
            track.state = TrackState.LOST
        if track.state in {TrackState.LOST, TrackState.REMOVED}:
            if track.track_id == self._target_track_id:
                # Both task modes require explicit reselection after a long
                # loss.  This latch survives delayed acquisitions whose
                # timestamp predates the output tick that expired the task.
                self._requires_reselection = True

    def _mark_missed(self, track: Track, timestamp: Optional[float]) -> None:
        track.age += 1
        track.missed += 1
        track._matched_this_frame = False
        if self.max_coast_duration_s is not None:
            if track.state not in {TrackState.LOST, TrackState.REMOVED}:
                track.state = TrackState.COASTING
            self._expire_by_time(track, timestamp)
        elif track.missed <= self.max_coast_frames:
            track.state = TrackState.COASTING
        elif track.missed <= self.max_lost_frames:
            track.state = TrackState.LOST
        else:
            track.state = TrackState.REMOVED
        if track.state in {TrackState.LOST, TrackState.REMOVED}:
            if track.track_id == self._target_track_id:
                self._requires_reselection = True

    def _association_cost(self, track: Track, detection: Detection) -> Optional[float]:
        if track.class_id != detection.class_id:
            return None
        iou = bbox_iou(track.bbox, detection.bbox)
        if self.association_mode == "iou_2d":
            return 1.0 - iou if iou >= self.association_iou_threshold else None
        track_position = None if track._filter is None or not track._filter.initialized else getattr(track._filter,"association_position",track._filter.position)
        detection_position = self._position_of_detection(detection)
        distance = None
        if track_position is not None and detection_position is not None:
            distance = float(np.linalg.norm(track_position - detection_position))
            if self.association_mode == "hybrid_3d":
                # Overlapping image boxes cannot bypass physically impossible
                # depth jumps. Use the same quality-dependent R as KF fusion.
                if distance > self.association_max_distance:
                    return None
                covariance = track._filter.measurement_covariance(
                    depth_stats=detection.depth_stats, confidence=detection.confidence,
                )
                mahalanobis = track._filter.mahalanobis_distance(
                    detection_position, measurement_covariance=covariance,
                )
                if mahalanobis > self.gate_threshold:
                    return None
            # A depth/3-D gate can associate boxes that do not overlap due to
            # fast image motion, but cannot bridge an implausible jump.
            if distance > self.association_max_distance and iou < self.association_iou_threshold:
                return None
        if iou < self.association_iou_threshold and distance is None:
            return None
        image_cost = 1.0 - iou
        if distance is None:
            return image_cost
        distance_cost = min(1.0, distance / self.association_max_distance)
        return 0.65 * image_cost + 0.35 * distance_cost

    def _merged_box_uncertainty_edges(
        self, candidates: Sequence[Track], detections: Sequence[Detection],
    ) -> set[tuple[int, int]]:
        """Recognize nearby box merges as uncertainty, never identity evidence.

        A merged box's centre/depth may move to another visible surface and
        fail a tight Mahalanobis gate. That rejection is still mandatory for
        fusion, but cannot justify creating a second identity over the same
        two recent objects. Require strong overlap AND growth relative to
        both prior boxes, and the existing physical distance bound to both.
        Depth-separated image crossings therefore do not trigger this guard.
        """
        if (self.association_mode != "hybrid_3d" or self._requires_reselection
                or self._pending_target_index is not None):
            return set()
        target = self.target
        if target is None:
            return set()

        def recent(track: Track) -> bool:
            # A timer can expire a competing hypothesis at output time before
            # an already-acquired frame reaches us. Its last accepted depth
            # may still be fresh at this frame's source time. Such a LOST
            # competitor may only add a freezing edge; it is never revived,
            # measured, or selected by this guard. A lost selected task is
            # excluded above by the irreversible reselection latch.
            source_fresh_lost_competitor = bool(
                track.state == TrackState.LOST
                and track.track_id != target.track_id
                and self.max_coast_duration_s is not None
                and self._timestamp is not None
                and track.last_measurement_timestamp is not None
                and 0.0 <= self._timestamp - track.last_measurement_timestamp <= self.max_coast_duration_s
            )
            if ((track.state not in {TrackState.CONFIRMED, TrackState.COASTING}
                    and not source_fresh_lost_competitor)
                    or track.hits < self.min_hits or track._filter is None
                    or not track._filter.initialized
                    or track.last_measurement_timestamp is None):
                return False
            if self.max_coast_duration_s is not None and self._timestamp is not None:
                return self._timestamp - track.last_measurement_timestamp <= self.max_coast_duration_s
            return track.missed <= self.max_coast_frames

        def area(box: Sequence[float]) -> float:
            return (box[2] - box[0]) * (box[3] - box[1])

        def merge_compatible(track: Track, detection: Detection) -> bool:
            if (track.class_id != detection.class_id or not recent(track)
                    or bbox_iou(track.bbox, detection.bbox) < 0.5
                    or area(track.bbox) <= 0.0
                    or area(detection.bbox) < 1.25 * area(track.bbox)):
                return False
            position = getattr(track._filter, "association_position", track._filter.position)
            return float(np.linalg.norm(position - self._position_of_detection(detection))) <= self.association_max_distance

        edges: set[tuple[int, int]] = set()
        for index, detection in enumerate(detections):
            if detection.position_3d is None or not merge_compatible(target, detection):
                continue
            if self._association_cost(target, detection) is not None:
                # A normal feasible merge is already handled by the strict
                # bipartite ambiguity graph below.
                continue
            for other in candidates:
                if other.track_id == target.track_id or not merge_compatible(other, detection):
                    continue
                edges.update(((target.track_id, index), (other.track_id, index)))
                self._merge_uncertainty_detection_indices.add(index)
        return edges

    def _associate(self, detections: Sequence[Detection]) -> tuple[dict[int, int], set[int], set[int]]:
        self._ambiguous_track_ids = set()
        self._ambiguous_detection_indices = set()
        self._merge_uncertainty_detection_indices = set()
        candidates = [
            track
            for track in self._tracks.values()
            if track.state != TrackState.REMOVED
            and not (self._requires_reselection and track.track_id == self._target_track_id)
        ]
        pairs: list[tuple[float, int, int]] = []
        for track in candidates:
            for index, detection in enumerate(detections):
                cost = self._association_cost(track, detection)
                if cost is not None:
                    pairs.append((cost, track.track_id, index))
        if self.reject_ambiguous_associations:
            # A bipartite component is safe only when every involved track
            # and detection has one edge. In a many-to-one merge, or one-to-
            # many split, choosing the lowest cost would manufacture identity
            # evidence. Freeze the entire component and reserve its boxes so
            # they cannot create duplicate tracks during the same ambiguity.
            by_track: dict[int, set[int]] = {}
            by_detection: dict[int, set[int]] = {}
            for _, track_id, index in pairs:
                by_track.setdefault(track_id, set()).add(index)
                by_detection.setdefault(index, set()).add(track_id)
            # These edges can only freeze a component. They are deliberately
            # absent from ``pairs`` and can never accept an observation.
            for track_id, index in self._merged_box_uncertainty_edges(candidates, detections):
                by_track.setdefault(track_id, set()).add(index)
                by_detection.setdefault(index, set()).add(track_id)
            frontier = [track_id for track_id, indices in by_track.items() if len(indices) > 1]
            frontier.extend(track_id for ids in by_detection.values() if len(ids) > 1 for track_id in ids)
            while frontier:
                track_id = frontier.pop()
                if track_id in self._ambiguous_track_ids:
                    continue
                self._ambiguous_track_ids.add(track_id)
                for index in by_track.get(track_id, ()):
                    self._ambiguous_detection_indices.add(index)
                    frontier.extend(by_detection[index] - self._ambiguous_track_ids)
            retired_tracks: set[int] = set()
            if self._pending_target_index in self._ambiguous_detection_indices:
                # A new explicit task selection may resolve stale competing
                # hypotheses after loss. Retire that whole old component and
                # reinitialize its visible boxes, so an obsolete alternative
                # cannot immediately steal/freeze the newly selected task on
                # its very next frame. The new UUID and new track IDs make
                # this discontinuity explicit in offline identity metrics.
                selected_component = list(by_detection[self._pending_target_index])
                released_indices: set[int] = set()
                while selected_component:
                    track_id = selected_component.pop()
                    if track_id in retired_tracks:
                        continue
                    retired_tracks.add(track_id)
                    self._tracks[track_id].state = TrackState.REMOVED
                    for index in by_track.get(track_id, ()):
                        released_indices.add(index)
                        selected_component.extend(by_detection[index] - retired_tracks)
                self._ambiguous_track_ids.difference_update(retired_tracks)
                self._ambiguous_detection_indices.difference_update(released_indices)
            pairs = [pair for pair in pairs
                     if pair[1] not in self._ambiguous_track_ids and pair[1] not in retired_tracks]
        pairs.sort(key=lambda item: (item[0], item[1], item[2]))
        matched_tracks: set[int] = set()
        matched_detections: set[int] = set(self._ambiguous_detection_indices)
        if self._pending_target_index is not None:
            # An explicit new image box is fresh task identity evidence. If
            # existing tracks are geometrically inseparable, initialize a new
            # track rather than assigning an arbitrary old identity to it.
            matched_detections.discard(self._pending_target_index)
        assignment: dict[int, int] = {}
        for _, track_id, detection_index in pairs:
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)
            assignment[track_id] = detection_index
        return assignment, matched_tracks, matched_detections

    def _update_track(self, track: Track, detection: Detection, *, timestamp: Optional[float] = None) -> bool:
        accepted = True
        track_timestamp = detection.timestamp if timestamp is None else float(timestamp)
        if track._filter is None:
            track._filter = self._new_filter()
        if detection.position_3d is not None:
            accepted = track._filter.update(
                detection.position_3d,
                timestamp=track_timestamp,
                depth_stats=detection.depth_stats,
                confidence=detection.confidence,
            )
            if accepted:
                track.last_measurement_timestamp = track_timestamp
                self._copy_filter_to_track(track)
            else:
                track.rejected_measurements += 1
                # An outlier is not a valid visual update; leave the track in
                # coasting state even though its image box matched the old box.
                self._mark_missed(track, track_timestamp)
                return False
        elif track._filter.initialized:
            track._filter.predict(timestamp=track_timestamp)
            self._copy_filter_to_track(track)
        # Commit the image/detector fields only after the optional 3-D gate has
        # accepted the measurement.  This prevents one bad depth sample from
        # dragging the association box away from a valid track.
        track.bbox = detection.bbox
        track.confidence = detection.confidence
        track.last_detection = detection
        track.last_update_timestamp = track_timestamp
        track.age += 1
        track.hits += 1
        track.missed = 0
        track._matched_this_frame = True
        if accepted:
            track.state = TrackState.CONFIRMED if track.hits >= self.min_hits else TrackState.TENTATIVE
        self._expire_by_time(track, track_timestamp)
        return accepted

    def _coast_track(self, track: Track, timestamp: Optional[float]) -> None:
        # Filters are predicted once for every active track at the beginning
        # of ``update_with_result``.  Do not predict again here: doing so would
        # double the elapsed time on empty frames without an explicit stamp.
        self._mark_missed(track, timestamp)

    def _eligible_tracks(self) -> List[Track]:
        return [
            track
            for track in self._tracks.values()
            if track.state in {TrackState.TENTATIVE, TrackState.CONFIRMED} and track._matched_this_frame
        ]

    def _apply_pending_lock(
        self,
        detections: Sequence[Detection],
        assignment: dict[int, int],
        new_track_by_detection: Optional[dict[int, int]] = None,
    ) -> None:
        if self._target_track_id is not None:
            return
        if self._pending_target_track_id is not None:
            track = self._tracks.get(self._pending_target_track_id)
            if track is not None and track.is_active:
                self._target_track_id = track.track_id
                self._target_uuid = self._pending_target_uuid or self._target_uuid or str(uuid4())
                self._pending_target_track_id = None
                self._pending_target_uuid = None
            return
        if self._pending_target_index is not None:
            index = self._pending_target_index
            self._pending_target_index = None
            if 0 <= index < len(detections):
                for track_id, detection_index in assignment.items():
                    if detection_index == index:
                        track = self._tracks[track_id]
                        if track.class_id == detections[index].class_id:
                            self._target_track_id = track_id
                            self._target_uuid = self._pending_target_uuid or self._target_uuid or str(uuid4())
                            self._pending_target_uuid = None
                        break
                if self._target_track_id is None and new_track_by_detection is not None:
                    track_id = new_track_by_detection.get(index)
                    if track_id is not None:
                        track = self._tracks[track_id]
                        if track.class_id == detections[index].class_id:
                            self._target_track_id = track_id
                            self._target_uuid = self._pending_target_uuid or self._target_uuid or str(uuid4())
                            self._pending_target_uuid = None
            else:
                self._pending_target_uuid = None

    def _select_auto_unique(self) -> None:
        if self._target_track_id is not None:
            return
        candidates = [track for track in self._eligible_tracks() if self.target_class is None or track.class_id == self.target_class]
        if len(candidates) == 1 and candidates[0].state == TrackState.CONFIRMED:
            self._target_track_id = candidates[0].track_id
            self._target_uuid = self._target_uuid or str(uuid4())

    def _update_status(self, *, ambiguous: bool = False, was_lost: bool = False) -> bool:
        target = self.target
        if target is not None and (
            self._requires_reselection or target.state in {TrackState.LOST, TrackState.REMOVED}
        ):
            self._status = TargetStatus.LOST
            return False
        if ambiguous:
            self._status = TargetStatus.AMBIGUOUS
            return False
        if target is None:
            self._status = TargetStatus.UNINITIALIZED
            return False
        if target._matched_this_frame:
            self._status = TargetStatus.REACQUIRED if was_lost else TargetStatus.TRACKING
            return was_lost
        self._status = TargetStatus.COASTING
        return False

    def predict_with_result(self, timestamp: float) -> TargetUpdate:
        """Return current-time snapshots without consuming a camera frame.

        Output-rate prediction must never advance the committed image/filter
        timestamp or increment missed-frame counts.  Otherwise a delayed 5 Hz
        detector cannot update a filter published at 50 Hz.  Optional second-
        based expiry still takes effect even when no new image arrives.
        """

        timestamp = float(timestamp)
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        if self._timestamp is not None and timestamp < self._timestamp - 1e-9:
            raise ValueError("prediction time must not precede image time")
        snapshots: dict[int, Track] = {}
        for track in self._tracks.values():
            self._expire_by_time(track, timestamp)
            snapshot = replace(track, _filter=None, _matched_this_frame=False)
            if track._filter is not None and track._filter.initialized:
                estimate = track._filter.project(timestamp)
                snapshot.position_3d = tuple(float(value) for value in estimate.position)
                snapshot.velocity_3d = tuple(float(value) for value in estimate.velocity)
                snapshot.covariance_3d = estimate.covariance[:3, :3].copy()
                snapshot.covariance_6d = estimate.covariance.copy()
            if snapshot.state not in {TrackState.LOST, TrackState.REMOVED}:
                snapshot.state = TrackState.COASTING
            snapshots[track.track_id] = snapshot
        target = snapshots.get(self._target_track_id)
        if target is not None and (
            self._requires_reselection or target.state in {TrackState.LOST, TrackState.REMOVED}
        ):
            status = TargetStatus.LOST
        elif ((self.mode == TargetMode.AUTO_UNIQUE and self._auto_unique_ambiguous)
              or (self.mode == TargetMode.LOCKED_TARGET and self._locked_ambiguous)):
            # Output prediction is not new visual evidence.  In particular,
            # it cannot clear the pause caused by several same-class objects.
            status = TargetStatus.AMBIGUOUS
        elif target is None:
            # Keep acquisition ambiguity visible before a target is selected.
            status = self._status
        else:
            status = TargetStatus.COASTING
        self._status = status
        self._last_result = TargetUpdate(
            target, status, tuple(snapshots.values()), timestamp,
            ambiguous_track_ids=tuple(sorted(self._ambiguous_track_ids)),
            ambiguous_detection_indices=tuple(sorted(self._ambiguous_detection_indices)),
            merge_uncertainty_detection_indices=tuple(sorted(self._merge_uncertainty_detection_indices)),
        )
        return self._last_result

    def update(
        self,
        detections: Iterable[Detection],
        *,
        timestamp: Optional[float] = None,
        target_index: Optional[int] = None,
    ) -> Optional[Track]:
        """Process one frame and return the current task target, if any.

        The returned object is the live :class:`Track` model.  For lifecycle
        status and all tracks, inspect :attr:`last_result` or use
        :meth:`update_with_result`.
        """

        result = self.update_with_result(detections, timestamp=timestamp, target_index=target_index)
        return result.target

    def update_with_result(
        self,
        detections: Iterable[Detection],
        *,
        timestamp: Optional[float] = None,
        target_index: Optional[int] = None,
    ) -> TargetUpdate:
        if detections is None:
            items: list[Detection] = []
        elif isinstance(detections, Detection):
            items = [detections]
        else:
            items = list(detections)
        if timestamp is not None:
            timestamp = float(timestamp)
            if not isfinite(timestamp):
                raise ValueError("timestamp must be finite")
            if self._timestamp is not None and timestamp < self._timestamp - 1e-9:
                raise ValueError("timestamps must be monotonic")
        # A per-call target index is equivalent to explicit first-frame locking.
        if target_index is not None:
            self.lock_detection(int(target_index))
        self._frame_index += 1
        # Detection timestamps are a useful fallback for callers that process
        # one synchronized frame at a time but do not pass a separate frame
        # timestamp.  This avoids mixing a filter's default dt with a zero
        # timestamp on the subsequent measurement update.
        frame_timestamp = timestamp
        if frame_timestamp is None and items:
            frame_timestamp = items[0].timestamp
        if frame_timestamp is None and not items and self._timestamp is not None:
            # Advance timestamped filters by their configured nominal period
            # even when an application omits a stamp on an empty frame.
            nominal_dt = float(self._kf_kwargs.get("default_dt", 1.0 / 30.0))
            frame_timestamp = self._timestamp + nominal_dt
        if frame_timestamp is not None and self._timestamp is not None and frame_timestamp < self._timestamp - 1e-9:
            raise ValueError("timestamps must be monotonic")
        self._timestamp = frame_timestamp if frame_timestamp is not None else self._timestamp
        filtered = [detection for detection in items if self.target_class is None or detection.class_id == self.target_class]
        for track in self._tracks.values():
            track._matched_this_frame = False
            # Expire against acquisition time before association too, so a
            # caller that never asks for output predictions still enforces
            # the same long-loss/reselection boundary.
            self._expire_by_time(track, frame_timestamp)
            if track.state != TrackState.REMOVED and track._filter is not None and track._filter.initialized:
                if frame_timestamp is not None:
                    track._filter.predict(timestamp=frame_timestamp)
                else:
                    track._filter.predict()
                self._copy_filter_to_track(track)
        assignment, matched_track_ids, matched_detection_indices = self._associate(filtered)
        was_lost = self.target is not None and self.target.missed > 0
        for track_id, detection_index in assignment.items():
            self._update_track(
                self._tracks[track_id],
                filtered[detection_index],
                timestamp=frame_timestamp,
            )
        for track in list(self._tracks.values()):
            if track.track_id not in matched_track_ids and track.state != TrackState.REMOVED:
                self._coast_track(track, frame_timestamp)
        new_track_by_detection: dict[int, int] = {}
        for index, detection in enumerate(filtered):
            if index not in matched_detection_indices:
                new_track = self._new_track(detection, timestamp=frame_timestamp)
                new_track_by_detection[index] = new_track.track_id
        self._apply_pending_lock(filtered, assignment, new_track_by_detection)
        candidates = [track for track in self._eligible_tracks() if self.target_class is None or track.class_id == self.target_class]
        if self.mode == TargetMode.AUTO_UNIQUE:
            # Count detector candidates before track confirmation/depth
            # acceptance: a second object with missing or rejected depth
            # still makes the unique-instance task ambiguous.
            if len(filtered) > 1:
                self._auto_unique_ambiguous = True
            elif len(filtered) == 1:
                self._select_auto_unique()
                target = self.target
                # Preserve task identity: the sole remaining object must
                # actually match the original track, rather than another
                # same-class track.  Empty frames never clear this latch.
                if target is not None and target._matched_this_frame:
                    self._auto_unique_ambiguous = False
            ambiguous = self._auto_unique_ambiguous
        else:
            if self._target_track_id in self._ambiguous_track_ids:
                self._locked_ambiguous = True
            elif self.target is not None and self.target._matched_this_frame:
                # Empty frames and timer projections are not identity evidence.
                self._locked_ambiguous = False
            ambiguous = self._locked_ambiguous or (self._target_track_id is None and len(candidates) > 1)
        reacquired = self._update_status(ambiguous=ambiguous, was_lost=was_lost)
        # Never select another target after a task target has been established,
        # even if it later becomes lost or a different candidate remains.
        self._last_result = TargetUpdate(
            target=self.target,
            status=self._status,
            tracks=tuple(self._tracks.values()),
            timestamp=self._timestamp,
            switched=False,
            reacquired=reacquired,
            associations=tuple(sorted(assignment.items())),
            ambiguous_track_ids=tuple(sorted(self._ambiguous_track_ids)),
            ambiguous_detection_indices=tuple(sorted(self._ambiguous_detection_indices)),
            merge_uncertainty_detection_indices=tuple(sorted(self._merge_uncertainty_detection_indices)),
        )
        return self._last_result

    step = update

