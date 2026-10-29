"""Stop only after final actual source correspondence and paused quiescence."""
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from uav_tracking.recording_closure import StreamDrainState,declared_truth_frames


def diagnostic(sample=1., *, accepted=True):
    return {"source_sample_s":sample,"source_publication_s":sample,
            "accepted":accepted,"odometry_header_s":sample if accepted else None,
            "reason":"validated_source_stamp" if accepted else "frame_locked"}


class RecordingClosureTests(unittest.TestCase):
    def test_pause_readiness_waits_for_timing_accepted_adapted_and_every_declared_gt(self):
        state=StreamDrainState(expected_truth_frames={'target':['actor0','actor1'],'vehicle':['uav']})
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        self.assertIn('no_observed_raw_with_corresponding_diagnostic',state.ready_to_pause(0.)['failures'])
        state.timing(diagnostic(),.1)
        self.assertIn('accepted_diagnostic_without_observed_adapted_odometry',state.ready_to_pause(.1)['failures'])
        state.adapted(1_000_000_000,.2)
        state.truth('target',[('actor0',990_000_000)],.3)
        state.truth('vehicle',[('uav',990_000_000)],.3)
        result=state.ready_to_pause(.3)
        self.assertFalse(result['ready'])
        self.assertEqual(result['missing_declared_truth_frames'],['target:actor1'])
        state.truth('target',[('actor1',990_000_000)],2.8)
        self.assertTrue(state.ready_to_pause(2.8)['ready'])
        # Initial delivery is not permission to weaken the final GT match.
        state.pause_ack(2.9)
        self.assertIn('missing_truth_at_final_clock',state.assess(3.5)['failures'])

    def test_pause_readiness_rejected_raw_does_not_wait_for_nonexistent_adapted(self):
        state=StreamDrainState(expected_truth_frames={'target':['actor'],'vehicle':['uav']})
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(accepted=False),.1)
        state.truth('target',[('actor',1_000_000_000)],.2)
        state.truth('vehicle',[('uav',1_000_000_000)],.2)
        self.assertTrue(state.ready_to_pause(.2)['ready'])
        self.assertEqual(state.ready_to_pause(.2)['counts']['adapted'],0)

    def test_pause_readiness_does_not_treat_unrelated_truth_callbacks_as_declared_frames(self):
        state=StreamDrainState(expected_truth_frames={'target':['actor']})
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(accepted=False),.1)
        state.truth('target',[('other_actor',1_000_000_000)],.2)
        result=state.ready_to_pause(4.)
        self.assertFalse(result['ready'])
        self.assertEqual(result['counts']['truth_target'],1)
        self.assertEqual(result['missing_declared_truth_frames'],['target:actor'])

    def test_no_pause_ack_or_unobserved_stream_cannot_claim_a_drain(self):
        state=StreamDrainState()
        self.assertFalse(state.assess(1.)["ready"])
        state.pause_ack(0.)
        result=state.assess(1.)
        self.assertIn("clock_not_observed",result["failures"])
        self.assertIn("raw_not_observed",result["failures"])

    def test_live_interleaved_latest_callbacks_do_not_hide_an_observed_complete_pair(self):
        state=StreamDrainState(expected_truth_frames={'target':['actor'],'vehicle':['uav']})
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(),.1)
        state.adapted(1_000_000_000,.2)
        state.truth('target',[('actor',1_000_000_000)],.2)
        state.truth('vehicle',[('uav',1_000_000_000)],.2)
        for index in range(2,10):
            state.raw(index*1_000_000,index*1_000_000,index)
            if index>2:
                state.timing(diagnostic(index-1),index+.1)
                state.adapted((index-1)*1_000_000_000,index+.2)
            result=state.ready_to_pause(index+.3)
            self.assertTrue(result['ready'])
            self.assertLess(result['observed_complete_source_us'][0],state.last_raw[0])
        # Readiness is permission to pause, never permission to close an
        # unmatched final stream or omit final-clock truth.
        state.pause_ack(10.)
        state.clock(9_000_000_000,10.)
        state.truth('target',[('actor',9_000_000_000)],10.)
        state.truth('vehicle',[('uav',9_000_000_000)],10.)
        self.assertIn('last_raw_without_corresponding_diagnostic',state.assess(11.)['failures'])
        self.assertIn('latest_diagnostic_does_not_match_last_raw',state.assess(11.)['failures'])
        state.timing(diagnostic(9),11.)
        state.adapted(9_000_000_000,11.1)
        self.assertTrue(state.assess(11.6)['ready'])

    def test_unrelated_raw_diagnostic_and_adapted_cannot_create_a_complete_pair(self):
        state=StreamDrainState()
        state.clock(3_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(2),.1)
        state.adapted(2_000_000_000,.2)
        self.assertFalse(state.ready_to_pause(.2)['ready'])
        state.timing(diagnostic(1),.3)
        self.assertFalse(state.ready_to_pause(.3)['ready'])
        state.adapted(1_000_000_000,.4)
        self.assertTrue(state.ready_to_pause(.4)['ready'])
        state.timing({'accepted':True},.5)
        self.assertIn('malformed_diagnostic_observed',state.ready_to_pause(.5)['failures'])

    def test_old_raw_evicted_from_bounded_history_cannot_establish_live_readiness(self):
        state=StreamDrainState()
        state.clock(300_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        for index in range(2,259):
            state.raw(index*1_000_000,index*1_000_000,index)
        self.assertEqual(len(state.observed_raw_keys),256)
        state.timing(diagnostic(1,accepted=False),300.)
        self.assertFalse(state.ready_to_pause(300.)['ready'])

    def test_delayed_diagnostic_and_adapted_delivery_extend_the_required_window(self):
        state=StreamDrainState()
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.pause_ack(.1)
        self.assertIn("last_raw_without_corresponding_diagnostic",state.assess(.8)["failures"])
        state.timing(diagnostic(),.8)
        self.assertIn("last_accepted_diagnostic_without_adapted_odometry",state.assess(1.4)["failures"])
        state.adapted(1_000_000_000,1.4)
        self.assertFalse(state.assess(1.89)["ready"])
        self.assertTrue(state.assess(1.9)["ready"])

    def test_cross_topic_reordering_can_deliver_adapted_before_diagnostic(self):
        state=StreamDrainState()
        state.clock(1_000_000_000,0.)
        state.adapted(1_000_000_000,.1)
        state.raw(1_000_000,1_000_000,.2)
        state.pause_ack(.3)
        state.timing(diagnostic(),.4)
        self.assertFalse(state.assess(.89)["ready"])
        self.assertTrue(state.assess(.9)["ready"])

    def test_rejected_last_raw_requires_its_diagnostic_and_no_adapted_message(self):
        state=StreamDrainState()
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,.1)
        state.pause_ack(.2)
        self.assertFalse(state.assess(1.)["ready"])
        state.timing(diagnostic(accepted=False),1.)
        result=state.assess(1.5)
        self.assertTrue(result["ready"])
        self.assertEqual(result["counts"]["adapted"],0)
        self.assertIsNone(result["expected_adapted_header_ns"])

    def test_another_raw_or_advancing_clock_resets_quiescence(self):
        state=StreamDrainState()
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(),0.)
        state.adapted(1_000_000_000,0.)
        state.pause_ack(.1)
        state.clock(1_100_000_000,.5)
        state.raw(1_100_000,1_100_000,.5)
        self.assertFalse(state.assess(.6)["ready"])
        state.timing(diagnostic(1.1),.6)
        state.adapted(1_100_000_000,.7)
        self.assertFalse(state.assess(1.19)["ready"])
        self.assertTrue(state.assess(1.2)["ready"])

    def test_a_newer_diagnostic_without_observed_corresponding_raw_cannot_pass(self):
        state=StreamDrainState()
        state.clock(1_100_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(),0.)
        state.adapted(1_000_000_000,0.)
        state.timing(diagnostic(1.1),.1)
        state.pause_ack(.2)
        self.assertIn("latest_diagnostic_does_not_match_last_raw",state.assess(1.)["failures"])

    def test_clock_republication_at_the_same_stamp_does_not_hide_quiescence(self):
        state=StreamDrainState()
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(accepted=False),0.)
        state.pause_ack(.1)
        state.clock(1_000_000_000,.6)
        self.assertTrue(state.assess(.6)["ready"])
        # Repeated raw delivery is real pending work even with the same stamp.
        state.raw(1_000_000,1_000_000,.6)
        self.assertFalse(state.assess(.7)["ready"])

    def test_malformed_diagnostic_does_not_pass_on_a_previous_valid_pair(self):
        state=StreamDrainState()
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(accepted=False),0.)
        state.pause_ack(.1)
        state.timing({"accepted":True},.2)
        self.assertIn("malformed_diagnostic_observed",state.assess(1.)["failures"])

    def test_all_declared_actors_and_vehicle_need_truth_at_the_exact_final_clock(self):
        state=StreamDrainState(expected_truth_frames={'target':['actor0','actor1'],'vehicle':['uav']})
        state.clock(1_000_000_000,0.)
        state.raw(1_000_000,1_000_000,0.)
        state.timing(diagnostic(accepted=False),0.)
        state.pause_ack(.1)
        state.truth('target',[('actor0',1_000_000_000),('actor1',990_000_000)],.2)
        state.truth('vehicle',[('world::uav',1_000_000_000)],.2)
        self.assertEqual(state.assess(1.)['missing_truth_frames_at_final_clock'],['target:actor1'])
        # A future sample alone does not replace evidence at the paused stamp.
        state.truth('target',[('actor1',1_010_000_000)],1.)
        self.assertFalse(state.assess(1.5)['ready'])
        state.truth('target',[('/world/actor1',1_000_000_000)],1.6)
        self.assertFalse(state.assess(2.)['ready'])
        self.assertTrue(state.assess(2.1)['ready'])

    def test_actual_single_and_multi_worlds_declare_every_logging_actor(self):
        root=Path(__file__).resolve().parents[1]/'ros2_ws/src/uav_tracking_bringup'
        for stage in (1,2,3):
            for cls in ('person','car'):
                frames=declared_truth_frames(root/'worlds'/f'stage{stage}_flight_{cls}.sdf')
                self.assertEqual(frames['vehicle'],['stage1_uav'])
                self.assertEqual(len(frames['target']),3 if stage==2 else 1)
        for cls in ('person','car'):
            frames=declared_truth_frames(root/'worlds'/f'stage3_multi_{cls}.sdf')
            self.assertEqual(frames['target'],[f'stage2_{cls}_{i}' for i in range(3)])

    def test_every_evaluation_pose_publisher_uses_the_documented_unthrottled_default(self):
        root=Path(__file__).resolve().parents[1]/'ros2_ws/src/uav_tracking_bringup'
        found=[]
        for folder in ('models','worlds'):
            for path in (root/folder).rglob('*.sdf'):
                for plugin in ET.parse(path).getroot().iter('plugin'):
                    if plugin.get('name')=='gz::sim::systems::PosePublisher' and plugin.findtext('topic','').startswith('/ground_truth/'):
                        found.append((path,plugin))
                        self.assertEqual(plugin.findtext('update_frequency'),'-1',str(path))
        self.assertEqual(len(found),16)


if __name__=="__main__":unittest.main()
