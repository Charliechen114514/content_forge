# 来源与致谢

本目录最初以 Git submodule 的形式引用：

- 项目：[op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh)
- 原 submodule 固定提交：`91f3d394db8419c20d67ebe22a96cf8fee0a404b`
- 上游许可证：MIT，全文见 [LICENSE.upstream](LICENSE.upstream)

感谢 Humanizer-zh 及其上游项目对中文 AI 写作模式、事实保真、作者声音和编辑边界的整理。本项目尤其认同这些原则：检查项不是作者身份检测器；模式命中不能代替上下文判断；普通排比、列表、破折号和连接词应按作用判断，不能机械删除。

## 当前目录与上游的关系

当前内容是 `content-forge` 维护的深度特调版本，不是上游仓库的镜像，也不宣称与上游命令、文件布局或规则集合兼容。它增加了：

- 面向本项目作者声音的正反语料；
- TOML 声明式规则与 Markdown 作用域；
- 纯标准库 Python 执行器；
- 历史误伤回归测试；
- 独立冷读审查与机械 lint 的边界。

Vale 仅作为规则资产模型的设计参考；本目录没有复制 Vale 的 Go 实现或英文规则包。

2026-09-26 起，本目录由 submodule 转为 vendored 维护。后续若移植 Humanizer-zh 的代码、文字或实质性规则，应在本文件记录来源，并继续保留其 MIT 许可证声明。
