# content-forge

纯文字加工平台:层卡写判据,清单选组合,烘焙器出角色包,复审验收把关。任何项目通过自包含的角色包使用它。

## 上手

```bash
./scripts/workchop bake        # 生成 build/<lane>/ 角色包(该目录不进 git,下文引用的 build/... 路径全由这一步产出)
./scripts/workchop doctor      # 环境体检(纯标准库,不 sudo)
./scripts/workchop cc-backup   # 换机前轻量备份 Claude Code 状态
```

`build/` 是生成物,在 .gitignore 里:新 clone 的仓库没有它,跑一次上面的 bake 就有,改层卡或清单后重跑即可,永远不要手改里面的文件。

## 任意项目改一篇文章

目标项目不需要采用这里的目录结构。只要 Agent 能读取 `content_forge`，在目标 Markdown 已经打开或已经明确给出路径时，直接说：

```text
请按照 content-forge 优化文章。
```

主控读 `build/single-editorial/master.md` 角色包（由 `recipes/` 层卡与 `combos/` 清单经 `workchop bake` 烘焙而来），目标取显式路径，取不到再看 IDE 当前活动的 Markdown，并从目标文件向上发现项目约束。平台随后按包派发通用 `content-writer` 与声音、保真、连续性、指代可解性四道走查。只有多个文件同样可能、又没有活动文件时，才需要追问目标。不要把内部调用模板重新甩给用户。

## 编写项目文档

如果要编写或优化 README、安装指南、配置说明和使用教程，就选 `project-docs` 组合。它默认写完整、直接的项目说明，不模仿个人口气；操作条件与完成检查要讲清，被动句与引用安排交给独立走查核对。

在仓库根目录运行：

```bash
python3 tools/bake.py project-docs
```

然后让 Agent 使用 `build/project-docs/master.md`，或者直接说“请按照 content-forge 的项目文档组合优化这份文档”。生成的包可以拷贝到其他环境使用，因为每个包都带有对应角色需要的规则全文。选层配置与人工回归案例见 [组合说明](combos/README.md)。

## 这里有什么

编辑链三件套:`recipes/` 层卡正本、`combos/` 选层清单(通用单篇流程 `single-editorial` 起步,可自建)、`tools/bake.py` 烘焙器,烘出自包含的 `build/<lane>/` 角色包,可拷贝分发。语料与机械检查住在 `tools/humanizer-zh/`。

架构 / 意图路由 / 部署细节见 **[AGENTS.md](AGENTS.md)**(真理源,AI 与人类共读)。

## 换机器 / 换 WSL

```bash
git clone <repo>            # 或直接拷贝目录
./scripts/workchop doctor   # 体检
./scripts/workchop bake     # 烘角色包
```

换机迁移 Claude Code 状态时,`./scripts/workchop cc-backup` 能帮上忙。
