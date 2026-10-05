# 流程:机械模式(mechanical)

| 层卡 | |
|------|------|
| 维度 | 流程 |
| 档位 | mechanical |
| 互斥 | five-gates(流程维度按任务模式选一) |
| 相邻 | 只换链接、去 frontmatter、转容器、统计图片、改排版这类活 |
| 让位 | 动了句子、段落边界或信息顺序就归 five-gates |

管辖声明:管机械校对类任务的边界与检查方式。

## 分清任务模式

不是每次改 Markdown 都要召集两个审稿员。启动任务时定下一种模式：

- `editorial`：改写、润色、生成技术发文包，或给出定稿建议。必须经过声音走查、内容保真走查、连续性走查、指代可解性走查和修改后复查。
- `mechanical`：只换链接、去掉 frontmatter、转 Markdown 容器、统计图片或改排版。不改句子与结构，只做机械校验。

任务一旦动了句子、段落边界或信息顺序，就归 `editorial`。不得用「只是轻微润色」逃掉复审。

## 机械检查的命令约定

- 收尾用 `python3 tools/humanizer_lint.py <目标.md>` 跑机械门禁，规则或语料有改动后,即跑 `python3 tools/humanizer_lint.py --self-test`。
- 规则与语料住在 `tools/humanizer-zh/`(上游项目,原址不动),本卡不抄规则本体。

## 来源

- 正文 = 原 REVIEW_WORKFLOW.md「先分清任务」一节（原文件已删除）。
- 机械检查命令约定为新写，收拢原 SOP 与审稿规约里的 lint 调用条款。
