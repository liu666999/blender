# RealHuman Studio — Implementation Audit

**Audit date:** 2026-10-15  
**Source branch:** `feature/realhuman-studio-phase1`  
**Scope:** Source-level review of `scripts/addons_core/realhuman_studio/`, the smoke-test script, and the workflow. This is not a claim that a full Blender GUI session or a Windows build has been tested.

## Project records

- [Project goals and task report](REALHUMAN_STUDIO_TASK_REPORT.md) — long-term vision, current phase, acceptance criteria and priorities.
- [Completed features](REALHUMAN_STUDIO_COMPLETED.md) — implemented capabilities and their verified boundaries.
- [Unfinished work](REALHUMAN_STUDIO_TODO.md) — missing features, manual validation and release tasks.

## Status legend

- **Implemented in source:** an operator or UI path exists in the checked-in code.
- **Headless smoke coverage:** the CI script exercises the path through Blender's Python API.
- **Needs visual/manual validation:** behavior depends on actual geometry, user interaction, GPU drawing, or deformation quality.
- **Not implemented:** no complete implementation was found in this phase.

## Implemented in source

| Area | Status | Notes |
|---|---|---|
| Project folders and JSON manifest | Implemented; smoke-tested | Creates models, anatomy, clothing, textures, exports, logs and `realhuman_project.json`. |
| Asset import and category collections | Implemented in source | Supports OBJ, FBX, GLB/GLTF, STL and PLY when the matching importer exists in the Blender build. |
| Asset import history and batch identity | Implemented; helper smoke-tested | Successful imports stamp each imported object with a batch ID and timestamp, and append source path, file size/mtime, category, object names/types and batch identity to an existing `realhuman_project.json` using an atomic replacement. If no project manifest exists, the import still keeps per-object metadata and reports that history was not written. |
| Selected asset audit report | Implemented; smoke-tested | Writes JSON diagnostics for selected objects: world bounds, dimensions in Blender units and estimated meters, source-file existence, import batch metadata, mesh counts, UV layers, materials, shape keys, armature links, loose geometry and non-manifold edges. Flags stale source paths, armature modifiers without targets, near-zero axes and heuristic size outliers (under 5 mm or over 20 m). Size flags are review prompts only because scene units and asset intent may be unknown; non-manifold edges can also be intentional on open garment borders. |
| Missing-source candidate scan | Implemented; smoke-tested | Recursively indexes supported source files under a chosen directory, finds same-filename/same-extension candidates for broken object paths, ranks file-size matches using project import history, and writes a JSON preview report. It never changes object paths or project history. |
| Batch repair from candidate report | Implemented; smoke-tested | Confirmation dialog revalidates unique same-name/same-extension/exact-size candidates against current object metadata and exactly one matching project-history batch. Only safe records are applied; ambiguous, changed, missing, conflicting, or inconsistent records are skipped. Updates object metadata and project history with atomic manifest replacement; does not reload geometry. Writes `logs/missing_source_repair_results.json` with per-object `repaired`/`skipped`/`failed` status, a reason code/message, candidate path, and expected/actual file sizes. Result writing is atomic and attempted for both successful repairs and rejected-only runs; manifest-write failure leaves object source paths untouched and records the failure where possible. |
| Repair result viewer | Implemented; automated helper/operator smoke tests added | Sidebar opens the result JSON, filters all/repaired/skipped/failed records, displays per-object reason and expected/actual sizes, and offers clipboard buttons for old and candidate paths. Shows up to 30 matching rows per dialog and reports when more remain in the full JSON. Tests cover filtering, malformed rows, valid/unsupported/missing report files, and operator registration/dispatch. Headless Blender cannot reliably validate system clipboard contents; actual clipboard behavior and graphical dialog rendering need manual Windows UI acceptance. |
| Source-file relinking | Implemented; smoke-tested | Relinks selected imported objects to an existing replacement source file, requires compatible extensions, rejects mixed import batches, and updates the matching `realhuman_project.json` batch with the new path, size, mtime and relink timestamp using an atomic file replacement. This only repairs source-path metadata; it does not reload or replace the current geometry. |
| Whole-project integrity audit | Implemented; smoke test added | Scans all objects in the current .blend, summarizes missing source files, missing armature targets, missing UVs/materials, suspicious dimensions and missing import-batch IDs, and cross-checks `realhuman_project.json` for missing source paths or object names absent from the current file. Writes `logs/project_integrity.json` by default when the configured project folder exists. Object-name history warnings are advisory because users may legitimately rename objects. |
| Selected asset manifest export | Implemented; smoke test added | Exports a portable `realhuman_studio_asset_manifest_v1` JSON document with Blender version, scene unit scale, source path/category, collections, world bounds and dimensions converted to meters, mesh/UV/material/shape-key statistics, armature references, and warnings when a linked armature is outside the selection. Metric conversion uses the scene unit scale and does not infer unknown source-file units. |
| Asset dimension and unit diagnosis | Implemented; smoke-tested | Writes world-space bounds, per-object dimensions/scales, scene unit settings, and heuristic meter/centimeter/millimeter interpretations to JSON. It never changes transforms; unit guesses are not authoritative because imported assets may have arbitrary coordinate conventions. |
| Selected asset position normalization | Implemented; smoke-tested | Non-destructively translates the selected object group so its X/Y bounds are centered and/or its lowest Z point sits at zero. Mesh coordinates and object scale are preserved; it does not infer real-world units or correct model orientation. |
| Category selection, visibility and reassignment | Implemented in source | Uses Blender collections and object metadata. |
| Height calibration | Implemented; unit conversion smoke-tested | Converts the target height in meters through the scene's `scale_length`, places the active mesh bottom at world Z=0, and rejects invalid unit scales. It changes only the active mesh object—not its armature, sibling meshes, or clothing—so use on a bound character requires care; it is not anatomy-aware proportion editing. |
| Selected-group height calibration | Implemented; multi-object and safety smoke tests added | Applies a uniform world-space scale to selected objects as a group, converts target meters through `scale_length`, and places the group's bottom at Z=0. It now cancels if a selected mesh references an armature modifier or armature parent that was not selected, avoiding a common partial-scale failure. Users must still select all clothing and other related assets; constraint-driven and complex rig setups require GUI validation. |
| Body proportion shape keys | Implemented; smoke tests cover invalid-geometry safety, custom-key preservation, and optional vertex-group masks | Generates reusable shoulder-width, chest-depth/width, waist, and hip-width shape keys with -1..+1 sliders. Uses smooth vertical weighting on a single upright Z-up mesh; artists may optionally create vertex groups named `RH遮罩 | 肩宽`, `RH遮罩 | 胸围`, `RH遮罩 | 腰围`, and `RH遮罩 | 臀宽` to limit each deformation. If a matching mask exists, unweighted vertices are not deformed by that control; if no mask exists, the original broad falloff remains. This is not anatomy-aware sculpting or a guarantee of realistic results on every topology. Geometry is validated before creating Basis. The mask boundary is smoke-tested on a cube only; real-human visual quality remains unverified. |
| Shape-key controls and reset | Implemented in source | Controls shape keys already present in the imported mesh. |
| GLB, FBX and OBJ export | Implemented in source | Depends on the exporter operator being available in the build. |
| Procedural fabric print | Implemented; shader construction smoke-tested | Dots, stripes or checker pattern with UV, object-local or generated coordinates; X/Y placement and scale controls; in Edit Mode, assigns the material only to selected faces. This is regional material assignment, not a full texture-painting or garment-pattern system. |
| Bounding-box-based simple humanoid rig | Implemented; rig-generation smoke-tested | Dialog exposes hip/knee/shoulder height ratios, shoulder half-width, and arm reach. These remain coarse initial estimates; final deformation quality is not certified by headless tests. |
| Starter poses and keyframe insertion | Implemented; smoke-tested | Keys local location, the active rotation representation, and scale for every pose bone. Existing Actions retain their names; only a newly created Action is named `RealHuman Motion`. |
| Selected-bone rotation editor | Implemented; headless smoke-tested | Sets local XYZ rotation on the active pose bone and can insert a rotation keyframe at the current frame; requires Pose Mode and an active bone selection. GUI discoverability and usability still need manual validation. |
| Named single-pose presets | Implemented; smoke-tested | Stored in the current scene as JSON custom data. |
| Named full-action sets | Implemented; smoke tests cover duplicate-name safety, persistence flag, load frame selection, and keyed transform evaluation | Duplicates an animation Action in the current .blend file. When a same-named saved Action is still used by another object, the save path creates a numbered copy rather than deleting that shared Action. Loading assigns the saved Action and moves the timeline to its first keyed frame; playback evaluation is smoke-tested, while save/reopen persistence still needs a separate file round-trip test. |
| Basic action-sequence checks | Implemented in source; smoke test added | Checks Action existence, frame range, one-frame clips and current-frame range; it does not judge animation quality. |
| Action JSON import/export | Implemented in source; smoke-tested | Samples local bone transforms per integer frame; converts the active local rotation matrix so Euler-animated bones are not exported with stale quaternion values; rejects unsupported rotation encodings on import; validates optional source-FPS metadata and warns on a mismatch without silently changing scene FPS. Not a lossless serialization of constraints, drivers, or NLA. |
| Standard views and body-facing presets | Implemented in source; smoke-tested | GUI context and actual view orientation still need manual checks. |
| Simple limb-clearance warning | Implemented in source; smoke-tested | A small set of bone-point distance heuristics, not mesh collision detection. |
| Shape-key-based expression/body reactions | Implemented in source | Requires imported models to contain suitably named shape keys; it does not create facial anatomy or muscles. |
| Minimal 2D stick-pose overlay | Implemented in source; keyframe and small-viewport layout smoke-tested | Circle head, simple body/limbs and four draggable endpoints; K records location, active rotation representation and scale for each pose bone. Existing Actions are not renamed; only a newly created Action receives the default `RealHuman Motion` name. A source-level layout defect that could clip the head in the smallest accepted viewport was corrected by aligning the minimum height check and center calculation. Actual GPU drawing, mouse interaction, view navigation and playback still require GUI testing. |

## Not implemented or still incomplete

- No bundled production-ready human base mesh, realistic skin material/texture library, anatomy meshes, or complete asset catalog.
- No complete procedural human generator, muscle/fat controls, or anatomical retopology. The new shoulder/chest/waist/hip shape keys are only a first-stage proportion tool.
- No complete anatomy simulation: toggles organize imported assets but do not generate bones, muscles, nerves, vessels, or organs.
- No robust garment pattern drafting, brush-based region painting, decal placement with arbitrary surface projection, or clothing simulation system. Regional face selection and coordinate-based procedural print placement are now available as a limited first step.
- No true 2D-to-3D inverse kinematics, joint-length solving, motion retargeting, contact-aware animation, or reliable mesh-collision solving.
- No visual quality guarantee for automatic skin weights, facial expressions, anatomical alignment, or mesh deformation.
- No standalone application shell, installer, Windows executable/package, custom scripting console, or full Python-like project execution environment beyond Blender's existing facilities.
- No third-party anatomy asset import pipeline with automated license review, semantic anatomy naming, unit conversion, or coordinate-system alignment. The selected-asset JSON audit is diagnostic only. Position normalization only translates the selected group; it does not apply transforms, infer real-world units, or correct model orientation.

## Real-human asset validation

- Added `REALHUMAN_STUDIO_ASSET_SOURCES.md` with the official Blender Studio Human Base Meshes v1.4.1 source and its listed CC0 license, plus a manual test procedure.
- Added `tests/realhuman_studio_real_mesh_validation.py` to generate/update the four proportion controls on a selected real-human mesh and export topology, UV/material/modifier, mask, and deformation-delta diagnostics to JSON.
- This helper is deliberately separate from the default smoke test: the 49 MB external bundle is not checked into the repository, and no actual real-human GUI run has yet been performed. The helper's coordinate metrics cannot certify anatomy, silhouette, clothing collision, or rig deformation.

## Known risks and manual validation checklist

1. Run the latest GitHub Actions workflow (the workflow now has a manual `workflow_dispatch` trigger) and confirm the Blender runtime smoke test reaches its explicit PASS marker, including import-history recording, per-item missing-source repair result reports, selected-asset and whole-project missing-source/rig-link diagnostics, Action-name preservation, and scale-keyframe checks.
2. In the actual GUI, register the add-on, generate the new shoulder/chest/waist/hip controls on an upright human mesh, and inspect for unwanted deformation; then check that the RealHuman sidebar draws without errors; enter Pose Mode, select a bone, adjust local XYZ rotation, and test optional keyframing.
3. Generate a rig from a representative human mesh; inspect bone positions, parenting, roll, and any automatic-weight deformation.
4. Test the 2D pose overlay from the sidebar in front, side, and perspective views; drag every endpoint, navigate with middle mouse/wheel, record multiple frames, and play the result back.
5. Save, close, and reopen a .blend file; confirm named pose presets and action sets remain available.
6. Test action-set name collisions with two rigs, confirm the existing shared Action remains assigned, and check frame playback after loading.
7. Check shader appearance for UV, object and generated coordinates on real garments; verify selected-face material assignment and exports in a separate viewer.
8. Test asset importers/exporters individually in the exact Blender build intended for daily use.

## Test interpretation

The headless smoke script exercises Python API paths, not real mouse input, GPU overlay rendering, visual rig quality, or Windows packaging. A successful smoke test is necessary but not sufficient for release readiness. Items marked as source-implemented must not be interpreted as visually verified unless a GUI test has actually been performed.

## Current recommendation

Continue in the requested order: finish CI-backed action-set regression checks; validate optional region masks on real human topology; run the documented CC0 real-human mesh diagnostic and inspect it visually; then complete Windows GUI acceptance for the sidebar, result viewer, pose overlay, rig and materials. After those gates, continue with unit/orientation-aware asset repair, better rig deformation, and the missing clothing/anatomy workflows. Keep bundled third-party assets as a separate, license-reviewed milestone.


## 2026-10-15 补充：动作集真实文件往返

新增 `tests/realhuman_studio_action_persistence.py`，以第二个 Blender 进程重开临时 `.blend`，核验命名动作集、fake-user 标记、骨架动作绑定与关键帧数值。CI 现已包含该脚本并编译整个 `tests` 目录。当前仅代表测试已编写并接入工作流；最新分支尚无对应 Actions 结果，不能记作运行通过。
## 2026-10-15 状态核对补充

- 已检查代码提交快照 `659592ae6b22adb50e4031191ae1037cfae66d2e`（之后仅有文档状态提交）与可见 Actions 运行记录。当前没有以该 HEAD 为测试提交的最新运行结果，不能宣称最近一轮测试通过。
- 旧运行 [38544308219](https://github.com/liu666999/blender/actions/runs/38544308219) 中 `python-syntax` 通过，`blender-runtime` 因旧版 smoke test 断言系统剪贴板精确内容而失败。剪贴板是无头环境限制，不应由后台 CI 检验真实系统剪贴板值；应在 Windows GUI 中手动复制并粘贴确认。
- 已静态核对动作集保存操作符 `action_set_name` 参数名与 `.blend` 往返测试调用一致。动作持久化测试仍需由匹配分支版本的 Blender 实际执行，之后才可更新为测试通过。
- 真实人体形态键、遮罩边界、骨架/服装穿插、简笔摆姿 GPU overlay 与侧栏布局仍分别需要真实人体数据或 GUI 验收。自动化几何位移指标只能证明网格坐标发生变化，不证明人体解剖或视觉质量合格。
## 2026-10-15 补充：Action slot 检查

- 测试脚本已对具有 `slots` 集合的复制 Action 显式设置 `rig.animation_data.action_slot`，避免仅赋值 `animation_data.action` 却未绑定 slot 的测试假阴性；在重开验证中同样检查 slot 关联与第 13 帧通道求值。
- 这项是测试可靠性修正，不是功能验收结论。提交 `28e0aaeb8a889d966af007bfc26556d7e8615973` 的 CI 尚未返回；如果目标 Blender 构建的 API 行为不同，应按日志调整，而不是跳过失败。
## 最新代码与运行证据（2026-10-15）

- 最近的测试代码提交为 `28e0aaeb8a889d966af007bfc26556d7e8615973`；最近 HEAD 为文档更新提交。Actions API 中没有该测试提交的运行，因此 Action slot 的修改尚未得到运行时验证。
- 本轮工具集没有 workflow dispatch 写入操作。测试需由仓库管理员/有权限用户在 [Actions 页面](https://github.com/liu666999/blender/actions/workflows/realhuman-studio-static.yml) 手动启动；获得运行日志后再继续修复。不要把没有触发的 CI 记作通过。

## 2026-10-15 补充：分层 Action 槽位绑定修正（待运行验证）

- 源码修正：载入命名动作集时，如果 Action 暴露 `slots`，操作会显式将骨架的 `animation_data.action_slot` 绑定到该 Action 的首个槽位，避免骨架仍持有旧 Action 槽位而导致新动作通道不求值。
- 回归测试：smoke test 新增载入后槽位绑定断言；`tests/realhuman_studio_action_persistence.py` 不再在重开文件后主动重绑槽位，而是直接断言保存的槽位绑定仍存在，避免测试自行修复待测状态。
- 本次代码提交：`717ed77e73aa60082ef715fd88c3a80ea941e390`（operator）、`23864c789bc1c755371c4f48435c700f1176d71d`（smoke test）、`7cb5587d1c963a074418765d347e4b891b475d8d`（.blend 往返测试）。
- **验证状态：仅完成源码与测试更新，尚未运行当前分支的 Blender runtime/CI；不得标记为通过。** 下一步继续核对 Actions 运行并根据真实日志修复，之后再按顺序进行真实人体网格验证和 GUI 验收。

## 2026-10-15 补充：保留动作集原始槽位身份（待运行验证）

- 进一步审查发现，动作集可能包含多个 Action Slot；仅绑定首个槽位不够稳妥，可能载入错误通道。
- 保存动作集时现在记录源骨架当前槽位的 identifier 到动作集自定义属性 `rh_studio_action_slot_identifier`；载入时优先按 identifier 选择槽位，旧动作集缺少该属性时再选择适用于 Object 动画的槽位，最后才回退到首槽位。
- smoke test 与 .blend 保存/重开测试已改为按保存的槽位身份检查，不再固定假设首槽位一定正确。
- 本轮提交：`9b389edee2d94cdc181ad24626af4574d71ae89b`（保存/载入槽位身份）、`67e9048017d0796779980acfa8cc17b6d1954770`（smoke test）、`d625d591c6f872e447c225fe0800cde88c8ffadf`（重开验证）。
- **状态：代码已提交，尚未在目标 Blender runtime 中执行；CI 结果仍待取得。** 本次修改没有被标记为测试通过。

## 2026-10-15 补充：保存动作集前验证有效 Action Slot（待运行验证）

- 代码审查发现：如果分层 Action 有槽位但骨架当前没有绑定有效槽位，保存流程会缺少可靠的源槽位身份，之后载入只能猜测。
- 现在在任何同名动作集替换/删除之前，先验证当前动作的槽位绑定有效；不满足时明确取消保存并提示用户选择有效槽位，避免错误保存或破坏已有动作集。
- 代码提交：`9d023b6731907643ca6fa56d8bc625987ad1a89f`。
- **状态：仅代码已提交，尚未运行 Blender runtime/CI；不代表测试通过。** 下一步仍优先获取动作集 smoke test 与真实 `.blend` 保存/重开测试结果，再进入真实人体网格验证。

## 2026-10-15 补充：动作槽位回归测试改为严格验证原始身份

- 进一步审查发现，原测试在找不到保存的槽位 identifier 时会回退到首个/兼容槽位，因此即使“原始槽位身份丢失”，测试也可能误通过。
- 已将 smoke test 与 `.blend` 保存重开测试改为严格断言：保存的 identifier 必须能在复制/重开后的 Action 中解析到真实槽位，且骨架绑定必须指向该槽位；不再用 fallback 掩盖身份丢失。
- 测试代码提交：`53dea5b582f6ea45b1246986e9520a95287fa2bb`、`94205d0294e9d36f8d0e326d2e751f0d1f004e4e`。
- **状态：测试断言已加强，但当前没有这些提交对应的新 CI run；尚未运行验证，不代表通过。** 若 Blender 的 Action.copy 确实会改变 slot identifier，这组测试会暴露问题，再按运行日志修复实现。

- 另新增 smoke regression：对支持 Action Slot 的版本，暂时解除源骨架的活动槽位后尝试保存同名动作集，要求操作被取消且旧动作集数据块仍保持原样；随后恢复原槽位。提交：`f3ff07b2f69a6bac028a71d99cb8e8cb91d340c3`。
- 此新增用例仍需 Blender runtime 实际执行；若目标 Blender 不允许把 `action_slot` 设为 `None`，将依据运行日志调整测试构造方式。

## 2026-10-15 审计补充：项目清单覆盖风险修复（待验证）

- **发现风险：** 项目目录已存在时，旧逻辑会直接用空 asset_sources 重写 realhuman_project.json，存在清空导入历史的风险。
- **修复策略：** 对现有清单做 JSON 结构与应用标识验证；有效清单不重写，错误清单拒绝操作；首次生成采用临时文件 + 原子替换。
- **测试策略：** 新增有效清单字段/导入历史保留断言，以及损坏 JSON 被拒绝且内容不变断言。
- **状态：** 源码与测试已提交，未取得最新 Blender runtime CI 结果；仍待自动化执行与实际 GUI 验收。

- 测试隔离注意：保留元数据的用例会在断言后重置 asset_sources 为空，避免影响后续导入历史追加测试；提交 5d2b0dba115826f6dc8fcb74869f0e29aa8fa9bc，尚未运行验证。

## 审计补充：动作 JSON 导入回滚（待验证）

- **风险：** 动作导入写入过程中若抛出异常，旧实现仅恢复 Action datablock，可能遗留部分骨骼姿态修改。
- **修复：** 保存全骨架变换快照；异常时恢复原 Action、可用的 Action Slot 与骨骼姿态，并清理无用户的临时 Action。
- **回归：** 非法 JSON 导入应保持当前姿态不变。
- **状态：** 已提交源码和测试，但尚未取得 Blender runtime 结果；真实写入中断路径仍待专门注入故障验证。

- 代码审查补充：恢复 Action Slot 时改为遍历现有 slots 并按稳定 identifier 比对，避免依赖集合的名称查找行为。提交：41984809e3cb1354fe7386345ec976fae1344d89；仍待 Blender runtime 验证。

## 审计补充：动作 JSON 部分写入失败路径（待验证）

- 新增 `_insert_action_json_keyframe` 包装点用于可控故障注入，生产路径依旧调用 Blender 的 `keyframe_insert`。
- 测试在首个关键帧写入后注入异常，检查取消结果、原 Action 与完整骨架姿态回滚。
- 代码提交 acc88d551a8d28f37202009f684726fc66a55977；测试 cb92fd6985b8875b3f479a3bc43e7e22cb030786；路径修正 1775490b240b2af64655deeb38d362f82ca0bf77。
- 当前未取得 runtime 结果，且需在目标 Blender 版本验证 orphan Action 清理与 Action Slot 恢复细节。

## 2026-10-15 新发现与修正（待验证）

- 风险：在异常分支恢复骨骼后，`finally` 恢复原帧可能重新求值原 Action，覆盖刚恢复的姿态快照。
- 修正：先恢复原帧，再重新应用 pose snapshot，最后更新视图层。
- 提交：09b6537d62d2e333cb4b372d849211958039e552。尚无对应 runtime CI 结果。

## 2026-10-15 复核发现

此前记录了“恢复原帧后重放姿态”，但最新读取的源码显示 finally 分支当时未实际包含重放逻辑。已在提交 `672b374ce6530d83213b402c3e0a282d57a78f16` 中补齐。此项是实际实现修正，待当前提交触发的 Blender runtime 测试验证。

## 2026-10-15 故障注入检查范围扩展

新增断言检查动作 JSON 中途写入失败后没有遗留新增的零用户 Action。提交：3fb885d7d319076ccef6c4eb2c92c1daa77bdf4f。该检查尚未由 Blender runtime 执行。

## 2026-10-15 导出操作符回归审计

- 发现此前替换 `finally` 时误将导入回滚变量引用带入 `RH_OT_export_action_json`，这会在导出动作时触发异常路径。
- 已在提交 `e32a8bf0e5d6806b395e0c5002118f477b812455` 中恢复导出操作符 finally：恢复原帧并更新视图层。导入操作符独立保留 `rollback_pose` 与 `pose_snapshot` 恢复。
- 该问题来自最近编辑，尚无运行结果；当前 HEAD 需要完整 smoke runtime 验证。

## 2026-10-15 测试审计补充：Action 泄漏检测

- 测试此前仅检查“名称新增且 users==0”的 Action，可能漏掉仍有用户引用的残留 Action。
- 已改为在故障注入前记录所有 Action 的 `as_pointer()`，失败后凡是出现新的 Action 数据块均判定为泄漏，不依赖名称或用户计数。
- 提交：`0b33c70df8b7b21c9ad3aa501a39b09b847f2b91`。测试仍待实际 Blender runtime 执行。

## 2026-10-15 导出写盘失败保护审计

- 发现原导出直接以 `w` 打开目标 JSON；若序列化中途失败，会截断先前有效文件。
- 已改为同目录唯一临时文件写入，序列化成功后 `os.replace` 原子替换；异常路径清理临时文件。
- 新增故障注入测试，模拟 JSON 序列化抛错并检查旧文件不变、临时文件不残留。测试夹具使用有效 JSON 字符串与换行。
- 实现提交 `1d204c795992133750eeafa30a4d731c241912e9`；测试提交 `b9ecdc75d18d5a31697be5efcc70df1deca6e73e`、`ddba9c7737a1a48769b9cb404eb5fa31971bbe28`。当前仅完成静态复核，Blender runtime 仍待执行。

## 2026-10-15 原子导出测试补充

- 在失败注入路径上增加场景帧恢复断言，避免导出异常后时间轴停留在采样帧。
- 增加成功覆盖路径：用新动作 JSON 替换已有文件，解析结果并确认格式标记有效，同时检查场景帧恢复和临时文件清理。
- 标准导出路径也检查原帧恢复。
- 测试提交：`88ec8c6167f64182616b70007b99e630943b8a01`。当前只完成代码审查，尚无该提交对应的 Blender runtime 结果。

## 2026-10-15 审计补充：资源清单导出保护（待运行验证）

- **风险：** 所选资源清单直接以写模式打开目标文件；JSON 序列化中途失败可能截断已有报告。
- **修复：** 新增 `_write_json_atomic`，在目标目录创建唯一临时文件，完成 JSON 序列化、flush 与 fsync 后通过 `os.replace` 替换目标，并在失败路径清理临时文件。
- **回归测试：** 注入序列化异常，断言操作取消、旧文件字节内容不变且无临时文件残留；恢复正常序列化后断言 schema 与导出成功。
- **状态：** 代码提交 `c95af719c116bfeb42fc14a3f5b5073f618c8849`，测试提交 `8e45299131a897ae26e7fb5d810a6d0ffc7ffcc0`。当前尚无对应 Blender runtime/CI 结果，不能标记通过。

## 2026-10-15 审计补充：动作集保存事务性

- **发现风险：** 旧实现先删除无真实使用者的同名动作集，再复制当前 Action；若复制失败，旧的可复用动作集会丢失。
- **修复：** 新增 `_copy_action_set_action` seam；先将副本写入唯一暂存名称、设置 fake user 和槽位元数据，再发布新名称。旧条目通过备份名暂存，只有新条目发布成功后才清理；异常时尝试恢复旧名称并删除暂存副本。
- **回归测试：** 注入复制异常，断言操作取消、旧动作集对象及名称不变，且没有暂存/备份 Action 残留。
- **状态：** 源码 `868f4265c96f8e26c0a0aef3f23ffb8dfcefb26d`，测试 `e0779a5d588f8f399221e322ed546783fa82f40f`。尚无 Blender runtime/CI 结果。

## 2026-10-15 审计补充：动作 JSON 畸形数据

- 新增零长度四元数与重复/非递增帧号回归用例，确保这类无效输入在动作写入前被拒绝，并且不会替换现有 Action。
- 测试提交 `95be5d54bb59cfc80b7c32e8b57903cfb48c4704`。当前只确认测试源码已写入分支，Blender runtime 尚未执行。


## 2026-10-15 审计补充：体型控制异常坐标污染

- **风险：** NaN/Infinity 顶点坐标可能使边界计算、衰减权重和生成的形态键坐标失效，且可能将坏数据扩散到整套控制。
- **修复：** 在任何 Basis 创建或既有键更新前检查基础坐标的 X/Y/Z 均为有限数；不符合时取消且不主动改动形态键。
- **回归：** smoke test 注入 NaN 顶点，断言操作取消且未创建 Basis。
- **提交：** 源码 `5edeafb4aad1c119e40332de7ff2fae39ff0f8d1`；测试 `107c119028f5f9ac9f76e6c2a5f6c77b2223c436`。
- **验证状态：** 代码审查与测试编写已完成，当前分支尚无对应 Blender runtime/CI 结果。


## 2026-10-15 审计补充：动作 JSON 四元数数值溢出

- **风险：** 输入四元数各分量虽然都是有限浮点数，但直接计算 sum(q*q) 可能溢出为无穷；随后除以无穷会把所有分量变成零，破坏旋转数据。
- **修复：** 先按最大绝对分量缩放，再计算缩放后长度并归一化。
- **回归测试：** 使用 [1e308, 1e308, 0, 0] 输入，检查导入完成且采样旋转四元数长度约为 1。
- **提交：** 源码 bbc69d6bf468d44b29025f6e96223ffe808e1e27；测试 b326d53e181ff749c9430826fde30d35f639890f。
- **状态：** 源码和测试已提交，尚未有当前提交对应的 Blender runtime/CI 结果。


## 2026-10-15 审计补充：资产导入器部分失败残留

- **风险：** 外部导入器可能在创建一个或多个对象后抛出异常，原异常处理只报告失败，未撤销已创建对象。
- **修复：** 导入前记录现有对象指针；异常时删除所有本次新建对象并解除其链接，再返回取消结果。
- **回归测试：** 注入一个“先创建网格对象、后抛出异常”的导入器，断言操作取消且对象指针集合与导入前一致。
- **提交：** 源码 c6315642a08f6ce49bd17c5e115165b308658364；测试 d9e8203dc1f09f8b9f670d8b05293ea4b08f0073。
- **限制/状态：** 目前只清理对象，不保证移除导入器新建的孤立数据块；当前提交尚无 Blender runtime/CI 结果。


## 2026-10-15 审计补充：孤立数据块清理范围扩展

- **风险：** 只删除导入失败后新增的对象，仍可能留下对象引用过的网格、材质或图像等孤立数据块。
- **修复：** 导入前记录常见数据块集合指针；异常路径先解除并移除新对象，再清理本次新增且 users 为 0 的数据块。
- **测试：** 故障注入在创建网格对象后抛错，断言对象与网格数据块集合都恢复到调用前状态。
- **提交：** 源码 ce0d4adbb0d4ac3e220dab318d13f0ab5663832c；测试 4aee1f4a0765f863fab416165e2b3a8145d63e88。
- **边界：** 当前只涵盖常见的指定数据块类型；测试和实现尚未在 Blender runtime/CI 实际执行。

## 2026-10-15 审计补充：导入清单与视口选择事务隔离（待验证）

- **风险：** 资源导入与项目清单已经完成后，视口选择/活动对象设置仍处于同一异常处理块。若上下文操作异常，异常处理会删除新对象，却无法撤回已写入的清单，造成“清单有记录、场景无资源”的状态漂移。
- **修复：** 将视口选择移至导入提交逻辑之外；捕获选择异常并给出警告，不再回滚已提交资源。项目导入历史改用 _write_json_atomic 统一原子写入。
- **回归：** 故障注入导入器创建一个对象并成功返回，随后让选择 helper 抛错；断言操作仍成功、对象保留且清单记录对应批次。
- **提交：** 源码 4f5e1dfdc6475254946e056acc78729a35670ef2；测试 93e6e5cc37c3604e629de15735350ea2cef34dbe。
- **状态：** 仅代码与测试已提交，尚无对应 Blender runtime/CI 结果。另一个仍待后续审查的边界是：如果分类移动或对象元数据写入阶段失败，异常清理需要继续核对新建分类集合与既有集合链接是否完全恢复。

## 2026-10-15 审计补充：分类阶段异常时回滚新建集合（待验证）

- **风险：** 分类 scaffold 创建的 Collection 可能已链接到场景或根集合；只按 users==0 清理无法保证失败后集合树回到原状。
- **修复：** 异常路径在删除新对象后，显式移除本次新建 Collection；如果原有根集合在操作前未链接当前场景，则尝试恢复该状态。
- **回归：** 注入分类移动阶段异常，故意创建临时 Collection，再检查对象和 Collection 的指针集合均与操作前一致。
- **提交：** 源码 a76fdc782e00ca35dd6738e554a2b49fd470f013；测试 9aaeb81cf9f3028351711ff06e7d47429ffccfc2、2f41f8f7190c50d2c1c5f81a914804bce4f00254。
- **状态：** 代码已提交，尚无当前提交对应的 Blender runtime/CI 结果。


## 2026-10-16 审计补充：导入器无对象成功返回的泄漏路径（待验证）

- **风险：** 导入器返回 `FINISHED` 但没有新增对象时，原逻辑提前返回 `CANCELLED`，没有经过统一清理；某些格式/异常插件路径若已创建材质、图像或集合，可能留下孤立数据块。
- **修复：** 将无对象结果提升为事务异常，进入已有回滚逻辑；回滚清理本次新增对象、无用户常见数据块与新建集合。
- **回归：** smoke test 注入仅创建材质、不创建对象的导入器，断言操作取消且材质数据块指针集合未变化。
- **提交：** 源码 `0176f9172360ec2b727d4c55a035187746b1b104`；测试 `c66bae52f0896ef47983f0c2ce3595b3dbc31259`。
- **状态：** 代码审查与测试编写完成，尚未在目标 Blender runtime/CI 实际执行。该回滚目前仍只覆盖已列出的常见数据块类型。
## 2026-10-16 审计补充：体型初始区域遮罩（待 runtime 验证）

- **此前的可用性缺口：** 体型形态键会读取可选的 `RH遮罩 | 肩宽/胸围/腰围/臀宽` 权重组，但面板没有创建这些组的入口；新手需要自行命名和配置。
- **实现：** 新增 `rh_studio.create_body_proportion_masks`，以 Basis 坐标（如存在）或网格顶点计算局部 Z 高度区间，并创建缺失的四个顶点组。区域中心与形态键规格集中定义，避免高度中心不一致。
- **非破坏性约束：** 已存在的同名组会直接保留，绝不重设其权重；新组仅为高度带内顶点赋 1.0，其余顶点不分配权重。若某区间没有顶点，不创建空组并向用户报告。
- **UI / 测试：** 侧栏已添加入口与局限提示；smoke 测试覆盖每区有权重、赋权顶点满足预期高度、将现有权重改为 0.25 后重复运行仍保留、不会产生重复组。
- **适用性限制：** 这不是自动人体分割；它假定人体网格在局部 Z 轴方向直立，高度带也可能选中相同高度的手臂或大腿。真实模型仍需要人工检查及权重绘制精修。
- **提交：** 源码 `ab85baa09a572a71a8942600fa06356afce18270`；UI `9470defc9158e4eb1cf72ac37fcc3681c2572f58`；测试 `da33f69b45361fc1cee3116adb058a275c853a9e`。
- **状态：** 静态复核完成；没有实际 Blender runtime/CI 结果，不能宣称测试通过。


## 2026-10-16 审计补充：基础体型轮廓模板

- **实现范围：** 新增 rh_studio.apply_body_silhouette_preset，提供男性基础、女性基础、运动型、纤瘦型、厚实体型五种起始值，作用对象严格限定为现有四个肩胸腰臀形态键。UI 已加入对应按钮；smoke 已加入模板数值与用户形态键隔离断言。
- **防误导边界：** 这些值是已有粗轮廓滑块的初始值，不表示完成真实的性别形态生成，也不创建肌肉/脂肪/五官/毛发资源。现有网格若没有对应 key 会跳过并提示；无任何匹配控制时取消，不修改模型。
- **变形质量风险：** 这些现阶段 shape keys 由网格局部 Z 高度衰减和 X/Y 轴缩放产生，不能代替真实解剖 morph targets。尤其是男女差异、肌肉走向、脂肪垂坠和关节过渡必须由专业基础模型、标注区域/遮罩和经验证的 morph 数据解决。
- **验证状态：** 源码 6b2ded12900d44179d7c2c3cd73a955b43a5b0c0、UI ff8c877d04528e22bd1822a87ad4464d0405fcf4、测试 e8741ec05bc97d131ddd0f0089c32753d791bc9a 已提交；尚无该提交对应的 Blender runtime/CI 结果。静态读取不等同于运行通过。

## 产品要求范围再次确认（2026-10-16）

后续验收基线需覆盖皮肤/皮下脂肪、骨骼、肌肉、血管、神经、内脏器官和毛发等独立结构；各层可以单独编辑，也可以统一调整；角色预设涵盖性别基础形态、身高、身体比例、脸型五官、肌肉/脂肪和毛发。雕刻目标是类似泥塑的真实笔刷工作流；布料目标是 UV 区域染色/浸染、图案印花、多图层和表面投射，而不仅是现有节点坐标调节。

上述系统均未因本次新增轮廓模板而视为完成。每个模块都需要实际资源、操作逻辑、测试和 GUI/视觉验收；当前先有可控的体型粗轮廓起点，真实解剖与雕刻/染印仍属于开发任务。


## 2026-10-16 审计补充：解剖类别扩充

- **变更：** 在类别枚举和集合映射中增加 FAT（脂肪层）、HAIR（毛发）、TISSUE（筋膜与其他组织），并把 ORGANS 标签明确为内脏器官。侧栏解剖图层面板依赖类别枚举循环，因此会自动包含新增类别。
- **回归覆盖：** smoke test 检查所需解剖分类同时存在于 CATEGORY_ITEMS 与 CATEGORY_COLLECTIONS；该断言只能检查代码结构，不能证明 Blender 的 Collection API 和 UI 实际正常。
- **提交：** 类别枚举 `5413c9f1b20c8a5ef23d0e1c73f282504d049435`；映射 `bbcfb167d4b10020639c3f78a1a41d04763032aa`；测试 `8eb09220b25e7ef4db462401b332a147c957876b`。模板按钮排布调整 `2f44013039f3337f74a1ba7787de4c2f3246ff93`。
- **风险/边界：** 新类别仅是资源容器及显隐分类，不会自动生成真实脂肪/毛发/筋膜；必须导入合规模型，并对层间对齐及统一缩放另行验收。当前没有对应的 Blender runtime/CI 通过证据。


## 2026-10-16 审计补充：开源解剖资产候选（未导入）

- **基础人体候选：** Blender Studio Human Base Meshes v1.4.1，官方 demo-file 页面将该资产包标为 CC0、约 49 MB、Blender 4.2+。仍需实际选取具体网格并运行真实人体验证脚本。
- **解剖候选：** GitHub 仓库 Charleeh/ecorche 的 README 声明模型为 CC BY-SA 4.0；含 634 个独立命名网格、骨骼/软骨/牙齿/眼部、深浅层肌肉和部分筋膜。其坐标单位、Y-up 朝向与 0.0001 根缩放需按上游说明验证。
- **已知缺失：** 单一成年男性，不含皮肤、脂肪、内脏、血管、神经，且无绑定/姿势。它不能满足完整人体需求，只是可组合的解剖部件来源。
- **许可边界：** 需随使用内容保留上游署名与 CC BY-SA 4.0 条件；不将模型资产错误地归为 CC0，也不在未经许可边界整理的情况下随 GPL 插件二进制打包。
- **验证状态：** 仅完成来源与 README 级别研究，未导入本项目、未核验实际 Blender 变换，也未检查每个部件的视觉对齐/质量。正式集成前仍需许可和技术复核。


## 2026-10-16 审计补充：浸染软边与织物微纹理节点

- **实现：** `RH_OT_create_fabric_print` 新增 DYE 模式、`edge_bleed` 与 `weave_strength` 参数；节点图由 Smoothstep `ShaderNodeMapRange` 控制染色/印花的软边混合，另用高频 Noise + Bump 给 Principled BSDF 的法线增加微细纹理。材质元数据保留坐标、位置、缩放、浸染软边、织纹强度以及独立的 `procedural_fabric_dye` 类型。
- **测试：** 新增烟雾断言验证节点存在、Map Range 接入颜色 Mix、Bump 接入 Principled Normal，并检查 DYE 参数元数据。源码 `bcf375a5a550d716a02a7719dc3cf913103de768`，元数据修正 `d2abb54163ecb85eedb42a95ad90ff64fea044d0`，UI `803ceb8d0a26b62fc0a03dea4a847000a41e1367`，测试 `f8d8f23831a11d10399b9e29ad3afcbe72bbf3eb` / `f6335cf02cbadbadd5247a9c578525f7dca9cdba`。
- **审计限制：** 节点平滑混色只提供视觉上类似染料渗开的边界，并未模拟液体扩散、纱线吸收、织物厚度或真实微纤维。高频 Noise 的效果也必须在真实服装上调整，程序节点构建成功不等于渲染质量合格。
- **验证状态：** 尚未取得当前提交对应 Blender runtime/CI 输出；相关回归测试不代表已通过。


## 2026-10-16 审计补充：统一角色控制器

- **实现路径：** 新增 `RH_OT_create_character_root` 与 `RH_OT_fit_character_root_height`。创建控制器时读取已分类的角色层集合，优先创建位于整体底部中心的 Empty，将无父级顶层对象接入并恢复原 `matrix_world`；已有父级的对象保留原有关系。整体身高校准读取控制器后代网格的世界边界，按 `scene.unit_settings.scale_length` 换算目标米制身高，统一缩放后再把最低点移至 Z=0。
- **回归覆盖：** smoke 在末尾清理测试场景后新建基础人体/皮肤两对象，测试父子关系、保持初始世界位置、根控制器平移传播、目标 1 米身高、底部 Z=0 和重复运行不复制控制器。
- **边界：** 挂接仅遍历非 `OTHER` 的分类图层；已有外部父级会被跳过并提示，不会自动判断外部父级是否属于角色；整个角色身高校准要求控制器保持直立（X/Y 旋转为零）。复杂绑定和真实多层解剖仍需 GUI 手测。
- **提交：** 算子 `9fda71a121ff45f929ec97b00207b1754986d2e2`；UI `53f75a84886b5d1e635804da734dd49abf5fe4ba`；测试 `a0d44e1b984a80fcfbe4378ba0e4a28995d448f9`。
- **验证状态：** 源码与用例已写入分支，未取得对应 Blender runtime/CI 结果；不可视为测试通过。


## 2026-10-16 本轮统一状态快照（以此节为最新汇总）

### 代码已提交、仍待 Blender runtime/GUI 验收

- **解剖图层分类：** 新增脂肪层、毛发、筋膜与其他组织分类；映射为独立 Collection，并测试分类枚举/映射覆盖。提交：`5413c9f1b20c8a5ef23d0e1c73f282504d049435`、`bbcfb167d4b10020639c3f78a1a41d04763032aa`、`8eb09220b25e7ef4db462401b332a147c957876b`。
- **体型粗轮廓模板：** 男性基础、女性基础、运动型、纤瘦型、厚实体型，仅设置现有肩胸腰臀形态键；测试模板数值与自定义键隔离。提交：算子 `6b2ded12900d44179d7c2c3cd73a955b43a5b0c0`、UI `ff8c877d04528e22bd1822a87ad4464d0405fcf4`、测试 `e8741ec05bc97d131ddd0f0089c32753d791bc9a`。
- **布料印花/浸染节点：** 新增 DYE 噪声染色、Map Range Smoothstep 软边和 Noise/Bump 微纹理，保留圆点/条纹/格纹及选中面应用；测试检查关键节点和实际连线。提交：材质图 `bcf375a5a550d716a02a7719dc3cf913103de768`、类型元数据 `d2abb54163ecb85eedb42a95ad90ff64fea044d0`、UI `803ceb8d0a26b62fc0a03dea4a847000a41e1367`、测试 `f8d8f23831a11d10399b9e29ad3afcbe72bbf3eb` 和 `f6335cf02cbadbadd5247a9c578525f7dca9cdba`。
- **统一角色控制器：** 新增 Empty 控制器，把已分类的人体、解剖、骨架和服装的顶级对象在保留世界矩阵的前提下统一挂接；增加按目标米制身高对整个角色组缩放和落地。保留已有对象父级以免随意破坏绑定。提交：算子 `9fda71a121ff45f929ec97b00207b1754986d2e2`、UI `53f75a84886b5d1e635804da734dd49abf5fe4ba`、测试 `a0d44e1b984a80fcfbe4378ba0e4a28995d448f9`，测试夹具清理 `1701818b4ade2105a066b1e8a08789aceb0c5436`。
- **开源资产研究：** Blender Studio Human Base Meshes v1.4.1 为基础人体候选；Écorché 为骨骼/肌肉候选，上游声明 CC BY-SA 4.0、成年男性单一姿态，缺少皮肤、脂肪、器官、血管和神经。尚未导入项目，正式集成前需要坐标/尺度/穿插/许可验证。来源清单提交 `bf001a85cde47a7b0be59d038df4927a02d8cb25`。

### 尚未完成的核心目标

完整真实人体与分层组织资产、真实女性/男性及体型/五官 morph 数据、肌肉和脂肪分布控制、皮肤与毛发生成、神经/血管/器官资产、泥塑式真实雕刻工具、UV 像素级笔刷和图层、真正的纤维/液体浸染物理模拟、服装版型/缝合/布料模拟与穿插适配，均尚未完成。当前程序化 DYE 是节点级视觉近似，不是物理液体扩散；当前形态键模板是粗轮廓初值，不是完整人体生成器。

### 验证状态

最新代码/测试提交没有可确认的 Blender runtime/CI 结果；GitHub 检查接口当前返回空状态。静态代码审阅和测试用例编写不等于测试运行通过。接下来应由真实 Blender runtime 执行完整 smoke suite，随后在真实人体、解剖结构与服装模型上做 GUI/视觉验收。