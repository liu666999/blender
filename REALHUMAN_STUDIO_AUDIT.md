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
