"""Independent static-mesh projection labels for the simulation study.

Only unoccluded, fully-in-frame examples may be called visible detection GT
without a renderer instance mask. The projection itself is an amodal box.
The mesh, visual transform, vehicle GT, camera calibration and timestamp
association are all recorded separately from the detector prediction.
"""
from __future__ import annotations
from bisect import bisect_left
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np


def quaternion_matrix(xyzw) -> np.ndarray:
    q = np.asarray(xyzw,dtype=float)
    norm = np.linalg.norm(q)
    if norm < 1e-12 or not np.isfinite(q).all():
        raise ValueError("Invalid quaternion")
    x,y,z,w = q/norm
    return np.asarray([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                       [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                       [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def rpy_matrix(roll: float,pitch: float,yaw: float) -> np.ndarray:
    sr,cr,sp,cp,sy,cy = np.sin(roll),np.cos(roll),np.sin(pitch),np.cos(pitch),np.sin(yaw),np.cos(yaw)
    return np.asarray([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                       [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])


def interpolate_pose(trajectory: list[dict], timestamp: float, tolerance_s: float=.10) -> tuple[np.ndarray,np.ndarray] | None:
    if not trajectory:
        return None
    times = [p["time_s"] for p in trajectory]
    index = bisect_left(times,timestamp)
    if index < len(times) and abs(times[index]-timestamp)<1e-9:
        row=trajectory[index]
        return np.asarray(row["position_m"]),quaternion_matrix(row["quaternion_xyzw"])
    if index==0 or index==len(times):
        return None  # No extrapolated truth.
    a,b = trajectory[index-1],trajectory[index]
    if max(timestamp-a["time_s"],b["time_s"]-timestamp)>tolerance_s:
        return None
    alpha=(timestamp-a["time_s"])/(b["time_s"]-a["time_s"])
    qa,qb=np.asarray(a["quaternion_xyzw"]),np.asarray(b["quaternion_xyzw"])
    if qa@qb<0:
        qb=-qb
    # Short-arc normalized interpolation; at 30 Hz rotations this differs
    # negligibly from slerp, and the method is explicitly recorded.
    q=(1-alpha)*qa+alpha*qb
    return (1-alpha)*np.asarray(a["position_m"])+alpha*np.asarray(b["position_m"]),quaternion_matrix(q)


def _collada_points(path: Path) -> np.ndarray:
    root=ET.parse(path).getroot()
    ns={"c":"http://www.collada.org/2005/11/COLLADASchema"}
    geometries={}
    for geometry in root.findall("c:library_geometries/c:geometry",ns):
        mesh=geometry.find("c:mesh",ns)
        if mesh is None:
            continue
        sources={s.attrib["id"]:s for s in mesh.findall("c:source",ns)}
        arrays=[]
        for vertices in mesh.findall("c:vertices",ns):
            for entry in vertices.findall("c:input",ns):
                if entry.attrib.get("semantic")=="POSITION":
                    source=sources[entry.attrib["source"].lstrip("#")]
                    array=source.find("c:float_array",ns)
                    accessor=source.find("c:technique_common/c:accessor",ns)
                    stride=int(accessor.attrib.get("stride",3)) if accessor is not None else 3
                    values=np.fromstring(array.text or "",sep=" ").reshape(-1,stride)[:,:3]
                    arrays.append(values)
        if arrays:
            geometries[geometry.attrib["id"]]=np.vstack(arrays)
    if root.findall(".//c:instance_controller",ns):
        raise ValueError("Skinned/animated controller meshes require renderer instance labels, not static vertex projection")
    output=[]
    def visit(node,parent):
        transform=parent.copy()
        for item in node:
            tag=item.tag.rsplit("}",1)[-1]
            if tag=="matrix":
                transform=transform@np.fromstring(item.text or "",sep=" ").reshape(4,4)
            elif tag in ("translate","rotate","scale"):
                raise ValueError("COLLADA TRS must be converted to matrices or explicitly supported")
        for instance in node.findall("c:instance_geometry",ns):
            points=geometries[instance.attrib["url"].lstrip("#")]
            output.append(points@transform[:3,:3].T+transform[:3,3])
        for child in node.findall("c:node",ns):
            visit(child,transform)
    active=root.find("c:scene/c:instance_visual_scene",ns)
    if active is None:
        raise ValueError("No active COLLADA visual scene")
    scene_id=active.attrib["url"].lstrip("#")
    scene=next(s for s in root.findall("c:library_visual_scenes/c:visual_scene",ns) if s.attrib["id"]==scene_id)
    for node in scene.findall("c:node",ns):
        visit(node,np.eye(4))
    if not output:
        raise ValueError("No static geometry in mesh")
    unit=root.find("c:asset/c:unit",ns)
    scale=float(unit.attrib.get("meter",1)) if unit is not None else 1.0
    axis=root.findtext("c:asset/c:up_axis",default="Y_UP",namespaces=ns)
    if axis!="Z_UP":
        raise ValueError("Only explicit Z_UP meshes currently supported")
    return np.vstack(output)*scale


def target_mesh_points(models_root: Path,target_class: str) -> tuple[np.ndarray,dict]:
    model=models_root/f"target_{target_class}"/"model.sdf"
    sdf=ET.parse(model).getroot()
    arrays=[]; sources=[]
    for visual in sdf.findall(".//visual"):
        mesh=visual.find("geometry/mesh")
        if mesh is None:
            raise ValueError("Target visual is not a mesh")
        uri=mesh.findtext("uri")
        if not uri or not uri.startswith("model://"):
            raise ValueError("Expected a model:// mesh URI")
        path=models_root/uri.removeprefix("model://")
        if path.suffix.lower()==".obj":
            vertices=[]
            with path.open(encoding="utf-8",errors="replace") as handle:
                for line in handle:
                    if line.startswith("v "):
                        vertices.append([float(v) for v in line.split()[1:4]])
            points=np.asarray(vertices)
        elif path.suffix.lower()==".dae":
            points=_collada_points(path)
        else:
            raise ValueError("Unsupported mesh format")
        scale=np.fromstring(mesh.findtext("scale","1 1 1"),sep=" ")
        pose=np.fromstring(visual.findtext("pose","0 0 0 0 0 0"),sep=" ")
        points=(points*scale)@rpy_matrix(*pose[3:]).T+pose[:3]
        arrays.append(points);sources.append(str(path))
    points=np.vstack(arrays)
    return points,{"sources":sources,"vertices":len(points),"model_local_min_m":points.min(axis=0).tolist(),
                   "model_local_max_m":points.max(axis=0).tolist(),"model_sdf":str(model),
                   "semantics":"Static render-mesh vertex silhouette extent; amodal projected box"}


def project_mesh(points_model: np.ndarray,target_pose,camera_pose,intrinsics,width:int,height:int) -> dict | None:
    target_position,target_rotation=target_pose
    camera_position,camera_rotation=camera_pose
    world=points_model@target_rotation.T+target_position
    optical=(world-camera_position)@camera_rotation
    if not len(optical) or np.any(optical[:,2]<=.10):
        return None  # Refuse near-plane partial geometry rather than distort GT.
    fx,fy,cx,cy=intrinsics
    uv=np.column_stack((fx*optical[:,0]/optical[:,2]+cx,fy*optical[:,1]/optical[:,2]+cy))
    low,high=uv.min(axis=0),uv.max(axis=0)
    if high[0]<=0 or high[1]<=0 or low[0]>=width or low[1]>=height:
        return None
    return {"bbox":[float(low[0]),float(low[1]),float(high[0]),float(high[1])],
            "fully_in_frame":bool(np.all(low>=1) and high[0]<width-1 and high[1]<height-1),
            "depth_range_m":[float(optical[:,2].min()),float(optical[:,2].max())],
            "box_type":"amodal_static_mesh_projection"}
