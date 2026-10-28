# v4 物理导航参考

`uav_tracking/core/navigation.py` 从对齐 RGB-D、相机标定、原采集时刻 TF 和显式类别尺寸先验估计地面目标参考。它不读取 SDF、Gazebo 实体名、真值 ID、冻结表面锚点或结果目录。本文描述新实现的受限几何能力；单元测试通过不等于实际飞行或任意视角中心定位已通过。

## 物理点与原有状态的关系

原有 `TargetState` 继续表达检测框中心射线与 ROI 深度构成的可见表面锚点，用于轨迹身份和云台视线。新 `NavigationEstimate.position_world_m` 表达目标地面足迹的中心：行人为受支持的脚底接地点，汽车为 upright 车体的地面投影中心。后者来自观测可见端面、侧面或相邻两个竖直面与声明的车体长宽高先验，并非观测到不可见车尾或自动识别车型尺寸。

控制器应使用独立导航状态滤波器，不把地面点混进原表面滤波器；两者必须绑定同一个任务 UUID、track_id 和采集时间。水平参考距离以目标地面中心为起点；高度参考应明确以哪个无人机物理点、垂直方向或地面法线计量。PX4 受控点、`base_link` 和仿真模型原点的固定结构关系必须显式声明，不能默认是同一点。模型原点误差仍应另列，不能只改评价器获得通过。

## 稳定接口

```python
from uav_tracking.core.navigation import (
    NavigationPrior, sample_depth_points, fit_ground_plane,
    estimate_footprint_from_points,
)

ground_camera = sample_depth_points(
    depth, intrinsics, exclude_bboxes=all_detected_boxes, max_points=800,
)
roi_camera = sample_depth_points(depth, intrinsics, bbox=selected_box, max_points=400)
# 下面两个数组必须由同一采集时刻的相机 TF 转入同一世界坐标系。
plane = fit_ground_plane(ground_world)
prior = NavigationPrior(
    class_name="car", length_m=declared_length, width_m=declared_width,
    height_m=declared_height, dimension_std_m=declared_dimension_std,
    prior_id="documented_vehicle_family",
)
reference = estimate_footprint_from_points(
    roi_world, ground_plane=plane, camera_position_world=camera_world,
    prior=prior, bottom_ray_world=world_ray_from_box_bottom,
    velocity_world=selected_track_velocity,
)
```

`sample_depth_points` 返回光学相机坐标 Nx3，过滤非有限、非正和超量程深度，确定性网格抽样并限制点数。深度默认以米计，毫米源必须显式传 `depth_scale=.001`。排除框为 xyxy，右下边界不包含在采样区间。

`GroundPlane` 满足 `normal·point + offset = 0`，法线指向声明的 up，包含 4×4 平面参数近似协方差、支持数、残差与有效性。`fit_ground_plane` 接受纯世界点云，使用有倾角限制的 RANSAC，拒绝支持不足、退化分布和过陡平面。图像便捷入口 `estimate_ground_plane` 要求显式相机到世界 4×4 刚体变换。

`NavigationEstimate` 提供位置、3×3 协方差、`valid/reason/reference_kind/support_count/heading_source/diagnostics`。无效结果不携带位置。`bottom_ray_world` 是以相机位置为起点的方向三向量；`heading_world` 可为世界 yaw 弧度或方向向量。没有显式 heading 时，仅超过声明速度门限的水平轨迹速度参与方向一致性诊断。几何解必须自身唯一，运动方向不能代替观测选择端面或侧面假设，也不能旋转已经测得的可见面法线。

## 观测条件与失败边界

地面估计必须排除所有检测框，不只排除所选框。有限点和法线约束不足以保证一片水平屋顶就是地面：适配器还需检查相机高度、目标邻近的地面支持范围、TF/深度新鲜度和不确定性。新参考不能因不断发布预测而刷新原始测量年龄，也不能放宽原有 0.60/0.75 秒安全门限。未知地面、长期无导航观测或参考歧义必须进入无效/悬停流程。

行人使用检测框底中点射线与地面交点，要求前景身体深度支持且脚点与身体地面投影一致。接近平行地面的射线、脚部遮挡、底部出画、背景污染或不一致几何不能被解释为可靠接地位置。纯点云入口不知道检测框是否截断，调用者必须传入前置质量判断；图像便捷入口会拒绝触及图像边界的框。

汽车从前景点拟合一个主要竖直面，再从其平面以外的剩余点寻找第二个独立竖直面。第二面必须达到支持数与占比要求；两个有支持的面若既不近似平行也不在正交角 ±15° 内，返回 `car_visible_faces_not_orthogonal`。接近掠视的面不能提供法向偏移，低高度支持或过窄/过宽的可见面不能作为有效导航参考。

单面同时检验“端面切向跨度为 W”和“侧面切向跨度为 L”两个解释。切向 5%–95% 分位跨度必须为声明尺寸的 0.65–1.25 倍；高度跨度必须为 H 的 0.25–1.35 倍。唯一端面解沿朝向相机的面法线向内退 L/2，唯一侧面解向内退 W/2，再投影到地面。面切向位置取分位范围中点，因此该方法仍依赖目标完整可见的前置条件。

双面分别检验“端+侧”和“侧+端”。每面至少满足对应切向尺寸的 0.40–1.25 倍跨度，因为独立平面的位置能够约束中心，不依赖部分可见面自身的中点。已知端面法向量 `n_e`、面常数 `d_e`，侧面为 `n_s,d_s`，地面为 `n_g,d_g`，中心解线性方程 `n_e·c=d_e−L/2`、`n_s·c=d_s−W/2`、`n_g·c=−d_g`。每种解释还要求至少 85% 前景点落在对应声明长宽的足迹范围内，横向容差 0.15 m。没有解时无效；存在两个解时返回 `car_static_end_side_ambiguous`，即使轨迹速度方向明确也不会猜选一个。有效类型保持 `car_cuboid_ground_center`，原因分别为 `car_upright_end_face_prior`、`car_upright_side_face_prior` 和 `car_upright_two_face_prior`。

转弯时，地面表面锚点的速度并不一定等于车体纵轴方向。现在以唯一可见面几何确定参考中心，运动方向仅报告与几何纵轴的一致性；错误或暂时转向的速度不会把中心旋转到错误位置。此变更不等于支持任意车辆形状：斜风挡、弧形车身、车顶、部分侧面恰好与端面形状相似，仍可能超出该先验模型。截断/遮挡/多目标重叠必须由调用者预先拒绝，任何几何解都不能覆盖前置无效判断。尤其单一部分侧面与完整端面在有限 RGB-D 下可能无法区分，不能宣称所有遮挡均可辨认。

尺寸先验误差直接影响中心：长度误差 ΔL 在端面模型下引入约 ΔL/2 的纵向误差，侧面对应宽度误差 ΔW/2。先验标准差默认各尺寸的 10%。单面协方差保留法向/切向尺寸误差和角度杠杆臂；双面将平面位置噪声、对应法向半尺寸方差和地面不确定性经过线性方程逆矩阵传播，再加入共同平面方向角的不确定性。该近似没有声称尺寸分布或表面模型已经标定。相机 TF 的不确定性必须由适配器额外传播。不得通过填零尺寸方差或从 v3 真值结果拟合固定补偿来掩盖误差。

## 验证与成本

纯 Python/NumPy 测试在 `tests/test_navigation.py`，26 项测试覆盖无效深度与所有框排除、抽样上限、带噪平面/斜坡/离群点、退化地面、行人射线交地、汽车静止端面唯一解释、完整侧面双侧视、双面位置约束与部分面中点偏差、带噪双面、错误运动方向、双解歧义拒绝、非正交面拒绝、掠视与部分面拒绝、刚体变换、先验失配和正定协方差增长。地面最多 800、ROI 最多 400 点的常用接线限制避免复制完整点云；RANSAC 次数有固定上限。实际耗时必须在目标运行环境测量，不能由点数上限推断达到实时要求。

实际验证须使用新的 v4 目录与计划：先验证行人和汽车无遮挡、静止及直线运动时的地面参考和真实距离/高度，再验证转弯、短遮挡、尺寸失配、空洞、坡面及不可观测场景。保留原 v3 源码、终态与失败，不重试或覆盖原槽位。单元测试、源码接线和新指标均不替代真实闭环证据。
