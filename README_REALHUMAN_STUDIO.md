# RealHuman Studio — Phase 1

RealHuman Studio is being developed inside this Blender source fork as a focused human-modeling workspace. The initial implementation deliberately builds on Blender's existing viewport, mesh, material, shape-key, rigging, and import/export systems rather than replacing them.

## Implemented in this phase

The add-on source lives in scripts/addons_core/realhuman_studio.

- Create a project folder layout (models, anatomy, clothing, textures, exports, logs) and a realhuman_project.json manifest.
- Import OBJ, FBX, GLB/GLTF, STL, and PLY assets into a chosen category, if the corresponding importer is available in the build.
- Create a collection hierarchy for base body, skin, bones, muscles, organs, nerves, vessels, clothing, rig, and other resources.
- Toggle category visibility and select all objects in a category.
- Move selected objects to a category.
- Uniformly scale the active mesh to a target world-space height and shift the bottom to Z=0.
- Expose existing shape-key sliders and reset non-Basis shape keys.
- Export selected objects to GLB, FBX, or OBJ, subject to exporter availability.
- Switch between front, back, left, right, top, and bottom views.
- Generate and assign a UV-based procedural fabric-print material with dot, stripe, or checker motifs; adjustable density, sparsity, rotation, base color, and print color.
- Generate a simple stick-display humanoid armature proportioned from a selected mesh's bounding box, with optional Blender automatic weights.
- Apply starter poses (reset/T-pose, relaxed, arms-up, sitting, wave) and insert animation keyframes at the current timeline frame.
- Apply basic expression presets by matching common English/Chinese names of shape keys already present on the active mesh.
- Save/load named pose presets inside the current `.blend` scene, add body-facing presets (front, three-quarter, side, back), and run a lightweight limb-clearance warning check.
- Trigger existing body-reaction morph keys for effects such as bulging veins or tense muscles, when the imported model actually provides those shape keys.

## Use

1. Build Blender from this fork using the official build instructions for your operating system.
2. Open Blender Preferences and enable RealHuman Studio from the add-on list if it is available in that build.
3. In the 3D View, press N and open the RealHuman tab.
4. Create the category scaffold, import a real human mesh, and assign anatomy meshes to the corresponding categories.

This repository commit is source code, not a prebuilt Windows installer or EXE. A Windows build has not been produced or tested by this commit. CI compiles the add-on's Python files and runs headless runtime smoke tests against multiple Blender LTS versions; it does not compile Blender or validate interactive GUI behavior.

## Not yet implemented

- No human mesh, skeleton, anatomy mesh collection, or skin textures are bundled in this phase. The fabric-print operator generates a procedural material; it is not a bundled library of textile assets.
- Shape controls reveal morphs already present in a model; the tool does not yet generate a parameterized human body from scratch.
- Height calibration is a scale operation, not anatomical retopology or proportion-aware reshaping.
- The app still runs on the Blender host UI; a finished standalone RealHuman Studio startup template and Windows packaging are future work.
- The asset repositories need a separate license-aware download, coordinate alignment, naming, and integration pass. Do not treat Git LFS pointer text as model data.
- The headless tests cover the basic operator paths, but automatic-weight quality and mesh deformation, bone orientation and final pose quality, clearance-warning accuracy, expression/shape-key matching, node-socket differences, UV behavior, and the interactive pose-pad overlay still need visual or GUI validation.
- The Blender C/C++ core is untouched in this phase.

## Runtime compatibility

- Development follows this GitHub source branch. Its `source/blender/blenkernel/BKE_blender_version.h` currently declares Blender 5.4.0 Alpha; the add-on metadata and runtime smoke test now use that branch version as the baseline rather than promising compatibility with older Blender releases.
- CI reads the Blender version and release cycle from the checked-out branch, locates a matching Linux x64 daily runtime, and runs the headless smoke suite against that runtime. When the branch's declared version changes, the test target follows it automatically.
- The headless runtime smoke test covers add-on registration/unregistration, rig generation, pose presets, keyframing, pose save/load, facing and clearance operators, fabric material construction, and project manifest creation. CI requires an explicit PASS marker, so a Python traceback inside Blender cannot silently pass the job.
- The headless test still cannot exercise interactive GPU overlay drawing or real mouse input; those need a GUI-session check. Blender daily builds can also change or break, so CI failures should be fixed against the checked-out branch rather than by silently downgrading the test runtime.

## License

New RealHuman Studio source files in this folder are licensed under GPL-3.0-or-later, as suitable for modifications distributed alongside Blender. Licenses for any later third-party assets must be reviewed separately and retained.

### 极简 2D 简笔摆姿
- 绘制内容精简为圆形头部、躯干和斜向四肢；不画肘、膝等中间关节点，只保留四个可拖动端点。
- 绘制目标区域固定到启动按钮所在 3D 视图的 `WINDOW` 区域，鼠标用窗口坐标换算，避免按钮位于侧栏时绘制/命中坐标错位。
- 拖动手部或脚部端点粗调对应手臂/大腿方向；`K` 记录当前帧所有骨骼关键帧，`R` 将简笔和受控骨骼复位到启动时姿势，`Esc` 或右键结束编辑。中键和滚轮继续交还视图导航。
- 世界轴旋转会考虑父骨骼当前姿态；记录关键帧时分别处理四元数、欧拉角和轴角旋转模式。
- 这是二维视图平面中的粗姿势控制，不是完整的二维到三维反解，不含自动肢体长度拟合或真实网格碰撞解算。仍需在实际 GUI 会话中检查不同视图朝向、模型绑定权重和关键帧回放；开发不再限定必须使用某一个 Blender 小版本。
