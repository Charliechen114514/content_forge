# Humanizer-ZH

这是一套面向本项目中文技术文章的文风规则，不是 AI 文本鉴定器。

本目录原先通过 submodule 接入 [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh)。感谢原项目整理中文 AI 写作模式，并坚持“保留事实、作者声音和文体，模式命中不能覆盖上下文”的编辑原则。随着本项目加入作者正反语料、Markdown 作用域、声明式规则和回归检查，它已经成为深度特调的本地版本，因此改为 **vendored 目录**：克隆 `content-forge` 即可取得完整资产，不再要求初始化子模块，也不会自动跟随上游更新。

本地规则还吸收了 [Vale](https://docs.vale.sh/topics/styles/) 的资产模型：**检查类型、Markdown 作用域、严重级别、说明文字和回归样本彼此分离**。没有复制 Vale 的 Go 实现或英文规则包；执行器仍是项目自己的纯标准库 Python 脚本。来源、分叉点和许可证边界见 [NOTICE.md](NOTICE.md)。

## 目录

```text
humanizer-zh/
├── corpus/
│   ├── VOICE.md          # 写手只读的短卡
│   ├── COMPARE.md        # 作者完整改稿工作坊（前后对照、问题、Tips）
│   ├── approved.toml     # 作者逐字原句
│   ├── annotations.toml  # 审稿分析与事实边界
│   └── rejected.toml     # 审稿反例
├── rules/          # 声明式 TOML 规则
├── tests/          # 正样本、反样本与历史误伤
├── NOTICE.md       # 上游致谢、分叉点与本地差异
└── LICENSE.upstream
```

规则支持五种检查：

- `existence`：在指定作用域中出现即提示；
- `absence`：指定作用域中没有出现任一目标模式即提示，当前用于段落人称硬门禁；
- `active_person`：段落没有人称，或者全部人称都只作「咱们的某某」式所有格时提示；
- `occurrence`：同一作用域片段中超过 `limit` 才提示。
- `clause_warmth`：逐个逗号/句号子句检查人称、承接或自然语气；语气词「呢」不能单独让子句通过。

目前的作用域有 `prose`、`visible`、`visible_raw`、`reader_visible`、`paragraph`、`list_item`、`heading`、`code_block` 和 `document`。`visible` 逐行覆盖标题、列表与普通散文，供硬禁词报告准确行号；`visible_raw` 保留行内代码与链接标记，只供需要识别「正文 `001`」一类 Markdown 指针的窄规则使用；`reader_visible` 还覆盖表格单元格，但仍剔除行内代码，供禁止字符一类必须遍历全部读者可见文字的规则使用。围栏代码只进入 `code_block`，frontmatter 与固定宣传块不扫描。

Humanizer 不提供 `warn` 或 `suggestion`。硬规则使用 `error`，命中后命令以失败退出。平衡句式和「用力动词 + 抽象名词」候选使用 `review`：它不是可忽略的提醒，而是强制升级信号，命中后必须在声音报告中完整引用原句、使用对应的显著标记并交主控二审；只有主控留下保留依据，正文才能带着该候选进入 READY。其他不足以阻断、也不需要强制升级的弱信号不要写成机械规则，留给冷读走查。

## 使用

```bash
python3 tools/humanizer_lint.py --self-test
python3 tools/humanizer_lint.py article.md
python3 tools/humanizer_lint.py -r document/journey/
python3 tools/humanizer_lint.py --format json article.md
python3 tools/humanizer_lint.py --list-rules
```

退出码只有两种：`0` 表示没有硬错误（可能仍有必须进入报告的 `review` 候选），`1` 表示至少存在一个 `error`。文本与 JSON 输出都会列出 `review` 候选。

## 新增规则的门槛

1. 先保存一个真实坏例子，说明坏的是词、句式、密度还是作用域。
2. 至少补一个会被相似正则误伤的好例子。
3. 能靠上下文判定、又不足以阻断交付的内容留给冷读审查，不放进机械规则库。
4. 运行 `--self-test`，再用一篇作者真迹和一篇待改稿做对照扫描。
5. 规则只提供线索，不自动改写；否则很容易把文章修成另一套模板。

## 更新上游参考

vendoring 以后，上游更新不会自动进入本目录。需要借鉴新版时，人工查看 Humanizer-zh 的变更，逐条判断是否符合本项目语料，再连同正反样本一起移植。不要用目录覆盖或自动同步冲掉本地规则。
