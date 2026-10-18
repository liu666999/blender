# RealHuman Studio — Real Human Mesh Validation Asset

## Primary validation asset

- **Asset:** Blender Studio / community Human Base Meshes, version **v1.4.1**
- **Official listing:** https://www.blender.org/download/demo-files/
- **Direct download:** https://mirror.blender.org/demo/asset-bundles/human-base-meshes/human-base-meshes-bundle-v1.4.1.zip
- **License shown by the official listing:** CC0
- **Bundle size listed by Blender:** approximately 49 MB
- **Minimum Blender version listed:** Blender 4.2 or newer
- **Why selected:** includes realistic and stylized human base meshes intended for sculpting, modeling, texturing, rigging, and simulation; avoids adding a large binary asset to this source repository.

Do not treat the bundle's CC0 label as applying to unrelated third-party assets downloaded elsewhere. Re-check the official listing and the bundle's own asset descriptions when selecting a specific mesh.

## Manual validation procedure

1. Download and unpack the official bundle from the source above.
2. Add one full-body realistic human mesh to a new Blender scene using the asset library workflow described by the bundle.
3. Enable the RealHuman Studio add-on and select the full-body mesh as the active object.
4. Run `tests/realhuman_studio_real_mesh_validation.py` from Blender's Text Editor.
5. Review `realhuman_studio_real_mesh_validation.json` beside the current `.blend` file.
6. In the GUI, set each shoulder/chest/waist/hip control to -1, 0, and +1. Inspect silhouette, mesh pinching, volume loss, intersections, UV/material stability, and whether the selected mesh's local axes match the tool's upright Z-up assumption.
7. If clothing and a rig are present, test them separately; this script does not certify clothing collision, skinning, or rig quality.

## Status and limitations

The validation helper records mesh topology counts, dimensions, UV layers, materials, modifiers, vertex groups, and evaluated mesh metrics at each control's negative and positive slider extremes. It restores all shape-key values that were present before the measurements. It is a diagnostic report, not a visual-quality score. Running it creates or updates the four RealHuman Studio shape keys on the selected mesh. Save a copy of the scene first.

**Current status:** source and license candidate identified; automated helper added. The asset has not been downloaded into this environment, and no real-human Blender GUI run has yet been performed. Do not mark real-human deformation quality as passed until the report and screenshots from an actual run are reviewed.


## Supplementary anatomy asset candidate: Écorché (bones + muscles)

- **Source:** https://github.com/Charleeh/ecorche
- **Model/download:** repository file `model/ecorche.glb` (README states about 13.7 MB); use the standard GLB, not the meshopt-compressed variant, for Blender import.
- **License:** model assets are stated in the source repository to be CC BY-SA 4.0. Required credit: “Écorché (github.com/Charleeh/ecorche), CC BY-SA 4.0. Based on BodyParts3D, © The Database Center for Life Science, CC BY 4.0, and Z-Anatomy by Gauthier Kervyn, CC BY-SA 4.0.” Distribute any modified model data under the required compatible ShareAlike terms and include the upstream notices.
- **Content claimed by upstream:** 634 named meshes; skeleton structures including 198 bones, 42 cartilages, teeth and eyes; deep and superficial muscles; a fascia sheet. Each structure has a separate named mesh, layer and side/source metadata.
- **Known gaps:** one adult male anatomical pose only; no female/child variant, no rig/poses, and it excludes organs, blood vessels, nerves, ligaments, joint capsules and skin. It complements the Human Base Meshes but cannot alone satisfy the full-character requirement.
- **Transform caution:** upstream README documents metre units, Y-up, figure facing +Z, soles on y=0, and a root scale of 0.0001. Validate the imported orientation and dimensions before any automatic transform; do not apply a blind scale to individual pieces.
- **Integration status:** research candidate only. The GLB has not been imported into the project or checked in Blender on this branch. Do not redistribute it inside the GPL source tree without retaining distinct third-party licensing and attribution.

## Resource combination strategy

Use Blender Studio Human Base Meshes v1.4.1 as the CC0 base-body candidate and Écorché as an optional CC BY-SA 4.0 skeleton/muscle source. Build each into clearly separated, named anatomy collections; store source URL, license, attribution and transforms in the project manifest. Do not assume the two assets share topology, coordinates, body proportions or compatible rigging. Organ/vessel/nerve/skin/fat/hair sources remain separate acquisition and per-asset license-review tasks. A visually aligned model is not proof that every included structure is anatomically or legally validated.


## 2026-10-18：原生 .blend 资产追加支持

- RealHuman Studio 资源导入器现在支持 .blend 文件：通过 Blender 的 library API 追加真实对象数据，再纳入既有分类、来源路径、导入批次和项目历史记录。
- 文件选择器与资源重新关联入口已加入 .blend 扩展名。
- 推荐的首个真实人体验证源仍是官方 Human Base Meshes v1.4.1，官方页面标注 CC0，约 49 MB，要求 Blender 4.2 或更新版本。下载/许可信息请以官方页面和压缩包内说明为准。
- 官方入口：https://www.blender.org/download/demo-files/
- 官方镜像：https://mirror.blender.org/demo/asset-bundles/human-base-meshes/human-base-meshes-bundle-v1.4.1.zip
- 注意：当前 .blend 导入会追加该文件中的所有对象，而不是弹出单个资产选择器。对于包含大量资产的库文件，建议先复制文件或使用单独的验证场景；后续可增加库内对象/集合选择。
- 自动化测试已新增临时 .blend 资源写入、追加、分类及来源元数据检查；尚未在 Blender runtime 中执行。


## 2026-10-18：按对象名选择导入的工作流更新

RealHuman Studio 导入器新增 .blend 精确对象名筛选：可以从上游库文件只追加指定对象，避免每次都导入整个库；留空则保持全量导入。对象名不存在会显式报错。此功能已增加 smoke test，但尚未在 Blender runtime 验证。

- 代码提交：fa4dec83bc7416295735a0c2ee3e03942efa076d
- 测试提交：f014852a3d61bbe3ddac3d5d2a9eb2a567ae64d
- 后续仍需真实资产验证依赖、集合归属、shape keys、UV、材质与许可；该功能不是资产本身，也不代表 Human Base Meshes 已导入项目。


## 2026-10-18：导入资产的来源与许可记录

导入器现在可记录上游来源网址、许可证名称和署名声明。对象会持久化这些自定义属性；项目 manifest 存在时也会记录到导入批次。未填写许可会被标记为 `UNVERIFIED`，不代表该资源可以合法使用。官方 Human Base Meshes 与 Écorché 等资源仍应逐项检查上游声明和具体资源条款。

- 代码提交：63e51249b6eb7fc5c6adcbf142139ccacb1bcecb
- 测试提交：cc42420e8c27cf4640ac8861a9eec8da9121cadb
- 尚未在 Blender runtime 验证。


## 2026-10-18：项目审计报告增加许可证状态与分类汇总

项目级审计 JSON 现在会汇总每种资源分类的对象数，并导出对象级来源 URL、许可证名称、许可状态与署名声明。若对象有资源分类或来源路径/URL，但许可状态不是 `verified`，报告会明确列为未独立核验。`verified` 是状态标记，不会自动验证许可；当前导入界面中的用户填写内容仍只是用户声明。

- 代码提交：`0de7e098a412b4405ab074c1e8da5a0b66547278`
- 测试提交：`5310621ae05bff4d75f6a008e8421306299c72bf`
- 尚未在 Blender runtime 执行。

测试夹具后续修正：在项目审计开始前给已存在对象设置许可元数据，修正测试提交 `7cf7abd54be3f8133befdf942600a56571524190`。Blender runtime 尚未验证。


## 2026-10-18：解剖分层完备度审计字段

项目完整性报告新增人体核心分类缺失检查，以及各分类网格、顶点/面、UV、材质、形态键统计。这些统计仅用于资产盘点和质量检查，不代表模型具备正确的人体解剖结构或各层拓扑对应关系。真实资产导入后仍需按具体来源、许可证、拓扑和结构逐项核验。

代码：`d917340cf2670a7cad0015149b19a57294d8ffb8`；测试：`d81bd7d9c6d5b5f32f9990c1fd3f46646699e15d`。尚未在 Blender runtime 运行。


## 2026-10-18：真实人体基底验证脚本增强

`tests/realhuman_studio_real_mesh_validation.py` 现在会报告：网格连通组件、游离顶点、边界边、非流形边、零面积面、UV 层及面覆盖率、材质槽使用情况、形态键与滑块范围；没有多边形的空网格会被拒绝。现有肩/胸/腰/臀控制仍会分别在 -1 与 +1 下测量评估后网格位移，并恢复运行前的形态键值。

- 提交：`7aa4345cab92dd93bb44882b8aa0427c801a246a`、`65317432a93a74dfc3bafd8bff83a03eec5162e0`
- 这些是诊断指标而非自动质量评分；边界边、多组件等情况需结合资产设计审阅。
- 尚未在 Blender runtime 运行，也尚未把 Human Base Meshes 下载或导入当前环境。真实人体基底的拓扑、UV、材质和形变质量仍待实际验收。


补充实现细节：边界边与非流形边现由 Blender `bmesh` 数据计算，避免依赖 MeshEdge 上不一定可用的属性。最终诊断脚本提交：`f81641c16140b1f510252c2de3fdba067f83fa8c`。

## 2026-10-18 继续开发：UV 完整性诊断修正

进一步改进真实人体网格验证脚本的 UV 检查：不再把“UV 向量对象存在”误当成 UV 有效，而是统计有限 UV 坐标覆盖率、非有限 UV 坐标、UV 面零面积情况，以及落在 0–1 方形外的 UV 坐标数量。特别注明：超出 0–1 范围可能是 UDIM/平铺纹理的有意设计，不能自动判错。

- 提交：`6a4d45b5d0b5b1a64ac9ace17698ccd8354e1e6e`
- 仍未在 Blender runtime 执行；这些统计需要对实际导入的真实人体网格生成报告后才有实测意义。

## 本轮资产验证补充：分层空间对齐审计

资源审计报告现可输出解剖分类的世界空间包围盒与对象变换，使用 `BASE_BODY` 作为粗略空间参照来提示明显尺寸或中心偏移。该功能不引入新的人体资产，也不证明任何外部资产已下载、授权已核验或解剖层已正确对齐。真实验证仍需导入许可清晰的完整人体网格并在 Blender 中检查。

- 对齐审计的 smoke-test 断言已加入 `tests/realhuman_studio_smoke.py`，但尚未运行，也尚未导入真实人体资产；不要将其视为真实资产验证结果。

## 多分类导入工作流补充

导入器现支持可选的对象名称到分类 JSON 映射，因此一个 `.blend` 或其他支持格式中若包含多个独立对象，可以分别归入基础人体、皮肤、肌肉等分类。映射按对象精确名称匹配；未映射对象使用默认分类。当前没有确认 Human Base Meshes v1.4.1 包内具体对象名称，因此示例名称只是格式示范，需在实际下载后核对。功能代码已提交，Blender 实测仍待完成。


## 2026-10-18：新增 .blend 资产库无损清点流程

新增 `tests/realhuman_studio_asset_inventory.py`，用于在 Blender 中检查解压后 `.blend` 资产库的实际数据块命名。使用方法：

1. 在脚本顶部把 `SOURCE_BLEND` 设置为真实 `.blend` 文件的绝对路径（不是 ZIP 压缩包路径）。
2. 在 Blender Text Editor 运行脚本。
3. 检查源文件旁生成的 `realhuman_studio_asset_inventory.json`，其中列出对象、集合、网格、骨架、材质、图片、动作、曲线名称与数量。
4. 根据真实对象名称配置 RealHuman Studio 导入器的精确对象筛选和 `category_map_json`，不要凭示例名称猜测。

该脚本只读取 `bpy.data.libraries.load` 的 `data_from` 名称，不将资产追加到场景、不修改源文件，也不判定模型解剖质量。提交：`fcd2044bfe6926b0958de9dccb58641aa2646344`。尚未在 Blender runtime 执行。
