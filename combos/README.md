# combos/ 选层清单

一个赛道一份 JSON,是这条线「装哪些层、派哪些角色」的唯一选择源。改口味改这里,再跑 `python3 tools/bake.py` 重新烘焙，build/ 是生成物,永远别手改。

## 字段

- lane:赛道名,产物落在 build/<lane>/。
- base:基座卡名,单值。所有线都装 forge-base。
- process:流程卡列表,按任务模式装(five-gates 加 mechanical)。
- review:审稿判据卡列表。
- voice:声音卡名,单值，可为 null。未选声音卡时不携带作者语料，写手与声音走查按场景和目标项目要求执行；选了声音卡时，单值键保证一次一份。
- scene:场景卡名,单值,可为 null(通用单篇线暂无场景卡)。
- roles:这条线派哪些角色。不需要某角色就少写一行(比如纯复审线不挂 writer)。
- role_layer_extras(可选):给个别角色加装层,键是角色名,值是维度列表。例如给 voice-walker 加装 review 层。

## 纪律

- 写手包不含 review 层、四道走查各拿各的判据,这是烘焙器里 ROLE_MATRIX 的结构保证,清单里写不进去。
- 语料(VOICE、COMPARE、approved)不在这里选:它们跟着 voice 层走,凡带 voice 的角色包按 ROLE_MATRIX 携带语料全文。
- 清单或层卡改动后,doctor 的「烘焙产物一致性」会核对产物与正本,漂移会拦。

## 项目文档组合

编写 README、安装指南、配置说明或使用教程时，选择 `project-docs.json`。这组默认不加载个人声音语料，因为读者需要的是完整、直接的项目说明；如果用户要求模仿作者，可以再指定真实声音材料。

在仓库根目录运行 `python3 tools/bake.py project-docs`，生成 `build/project-docs/` 下的六份角色包。使用时让主控读取其中的 `master.md`，其余角色也读取这组对应的包。

场景卡给出文档的读者与写作方向，审稿卡负责操作完整性、项目事实、被动句与引用安排。写手不读审稿层；声音、保真和连续性走查通过 `role_layer_extras` 分别取得对应判据，再各自检查表达、事实和引用安排。人工回归案例在 `tests/project-docs-cases.md`。
