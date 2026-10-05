# content-forge — 纯文字加工平台

> **一句话**:一个纯文字的加工平台。层卡写判据,清单选组合,烘焙器出角色包,复审验收把关。本平台不携带任何业务内容,任何项目通过自包含的角色包使用它。

**本文件只负责平台路由与工具边界。** Claude Code 读 `CLAUDE.md`(软链到本文件),Codex 直接读本文件——两边同源。编辑判据住 `recipes/` 层卡。

## 快速命令

```bash
./scripts/workchop bake [lane] # 烘焙角色包(--check 只对账不写文件)
./scripts/workchop doctor      # 环境体检
./scripts/workchop review ...  # 稿件复审留痕与 READY 验收
./scripts/workchop cc-backup   # 轻量备份 Claude Code 状态(换机用)
```

## 意图路由(你说一句话 → 进这里)

| 用户意图关键词 | 路由到 | 入口动作 |
|----------------|--------|----------|
| 「请按照 content-forge 优化文章」/ 使用 content_forge 改写 / 润色任意 Markdown / 单篇走查 | 通用单篇流程 | 主控读 build/single-editorial/master.md（combos/single-editorial.json 选层，workchop bake 生成），目标取显式路径或 IDE 活动 Markdown，再自动发现项目约束并按包派发写手与四道走查 |
| 体检 / 环境 / 装环境 / 坏了 / 换电脑 | 平台 | `workchop doctor` |

本平台只管文字加工。发布、排期、业务待办不在路由内,由使用方自管。歧义时(意图不明)→ 问用户,不要猜。

## 任意项目接入

`content_forge` 的编辑流程不依赖任何固定仓库布局。用户只需说「请按照 content-forge 优化文章」，主控读 build/single-editorial/master.md 角色包（由 recipes/ 层卡与 combos/ 清单烘焙而来），从显式路径或 IDE 活动文件确定目标，并向上发现该项目自己的约束文件与事实材料。项目约束决定能改什么和事实是什么，角色包里的层卡判据、流程与作者语料决定怎样写、怎样验。外部环境接入就是拷贝 build/<lane>/ 整目录——包自包含，拷走即用，收尾机器检查够不着仓库时降级为模型走查加人工验收。

通用角色位于 `.claude/agents/`：

- `content-writer`：完整文件写手。
- `content-voice-walker`：独立声音走查。
- `content-fidelity-reviewer`：独立事实保真走查。
- `content-thread-walker`：独立连续性走查。
- `content-reference-walker`：独立指代可解性走查。

运行环境不能自动发现这些 Agent 定义时，主控把 build/ 里对应的角色包分别交给独立上下文。不能退化成同一个 Agent 一边生成、一边宣告自己通过。

## 全局约定

- **写作与复审的宪法**(指令裁决顺序、内容保真不等于句式保真、编辑性任务不能自证通过、编辑边界)唯一正本是 `recipes/base/forge-base.md`,随角色包生效。AGENTS.md 只负责平台路由与工具边界,不复述第二份。
- **平台脚本纯标准库**(python3,无 venv、无第三方依赖)。
- **本平台不携带业务内容**:选题、发布、登记、笔记一律住在使用方自己的仓库里。

## 平台层文件速查

| 路径 | 内容 |
|------|------|
| `recipes/` | 层卡正本(宪法、流程、审稿判据、声音策略、六张角色卡),改口味改这里 |
| `combos/` | 选层清单,一条流水线一份 |
| `tools/bake.py` | 烘焙器:combos 加 recipes 烘出 build/<lane>/<角色>.md 角色包 |
| `build/` | 烘焙产物(gitignore,`workchop bake` 按需生成，包自包含,可拷贝分发) |
| `tools/humanizer-zh/corpus/VOICE.md` + `COMPARE.md` + `approved.toml` | 作者声音语料原文正本，烘焙时全文进写手与声音走查包 |
| `.claude/agents/content-*.md` | 五张薄壳,指向 build/ 角色包，其他 Agent 环境直接把角色包交给独立上下文 |
| `scripts/workchop` | 统一入口 dispatcher(bake / doctor / review / cc-backup) |
| `scripts/doctor.py` | 环境体检 |
| `scripts/backup_claude_code.py` | 轻量备份 Claude Code 状态并生成换机恢复指南 |
| `scripts/review_gate.py` | 建立复审单、归档报告、检查源稿/成稿版本与 READY 状态 |
| `tools/humanizer_lint.py` | Humanizer-ZH 执行器(Markdown 作用域、文本/JSON 输出、错误退出码) |
| `tools/humanizer-zh/` | 声明式中文文风规则、规则回归与按场景挑选的正反语料，新增规则后即跑 `humanizer_lint.py --self-test` |

## 部署(换电脑 / 换 WSL)

1. `git clone` 本仓库(或拷贝目录)。
2. `./scripts/workchop doctor`(纯标准库,不 sudo),再 `workchop bake` 烘出角色包。
3. 任意项目接入:拷 `build/<lane>/` 角色包过去,或让主控读本仓路径。
