# combos/ 选层清单

一个赛道一份 JSON,是这条线「装哪些层、派哪些角色」的唯一选择源。改口味改这里,再跑 `python3 tools/bake.py` 重新烘焙，build/ 是生成物,永远别手改。

## 字段

- lane:赛道名,产物落在 build/<lane>/。
- base:基座卡名,单值。所有线都装 forge-base。
- process:流程卡列表,按任务模式装(five-gates 加 mechanical)。
- review:审稿判据卡列表。
- voice:声音卡名,单值。单值键装不下第二份,互斥在这里由数据结构保证。
- scene:场景卡名,单值,可为 null(通用单篇线暂无场景卡)。
- roles:这条线派哪些角色。不需要某角色就少写一行(比如纯复审线不挂 writer)。
- role_layer_extras(可选):给个别角色加装层,键是角色名,值是维度列表。例如给 voice-walker 加装 review 层。

## 纪律

- 写手包不含 review 层、四道走查各拿各的判据,这是烘焙器里 ROLE_MATRIX 的结构保证,清单里写不进去。
- 语料(VOICE、COMPARE、approved)不在这里选:它们跟着 voice 层走,凡带 voice 的角色包按 ROLE_MATRIX 携带语料全文。
- 清单或层卡改动后,doctor 的「烘焙产物一致性」会核对产物与正本,漂移会拦。
