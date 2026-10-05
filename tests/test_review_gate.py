import importlib.util
import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("review_gate", ROOT / "scripts/review_gate.py")
review_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(review_gate)


class ReviewGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.review_home = self.root / "review_home"
        self.review_home.mkdir()
        self._old_home = os.environ.get("CONTENT_FORGE_REVIEW_HOME")
        os.environ["CONTENT_FORGE_REVIEW_HOME"] = str(self.review_home)
        self.package = self.root / "package"
        self.package.mkdir()
        (self.package / "article.md").write_text("# 题目\n\n咱们来看正文。\n", encoding="utf-8")
        self.source = self.root / "source.md"
        self.source.write_text("# 源稿\n", encoding="utf-8")

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("CONTENT_FORGE_REVIEW_HOME", None)
        else:
            os.environ["CONTENT_FORGE_REVIEW_HOME"] = self._old_home
        self.tmp.cleanup()

    def init(self, mode="editorial"):
        args = Namespace(package=self.package, lane="demo", mode=mode,
                         source=str(self.source), reset=False)
        self.assertEqual(review_gate.cmd_init(args), 0)

    def record(self, check, verdict="PASS"):
        if check == "recheck":
            (self.package / "review/resolution.md").write_text(
                "# 问题处理\n\n四份走查报告均无阻断项。\n", encoding="utf-8")
        report = self.root / f"{check}.md"
        report.write_text(
            "## 范围\n\n已逐段检查全文、修改处的上下文、代码块与链接边界。\n\n"
            "## 问题\n\n未发现新的阻断项，句子与相邻段落能够自然承接。\n\n"
            f"## 结论\n\n{verdict}\n", encoding="utf-8")
        args = Namespace(package=self.package, check=check, verdict=verdict, report=report)
        self.assertEqual(review_gate.cmd_record(args), 0)

    def test_balance_quote_extracts_sentence_instead_of_whole_paragraph(self):
        lines = ["前一句已经结束。动工不是写代码，是画地图——后面还有解释。末句继续。"]
        item = {"line": 1, "hit": "不是写代码，是"}
        self.assertEqual(
            review_gate.finding_sentence(lines, item),
            "动工不是写代码，是画地图——后面还有解释。")

    def test_editorial_requires_all_checks_and_current_recheck(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        self.record("continuity")
        self.record("reference")
        self.record("recheck")
        self.assertEqual(review_gate.assess(self.package), (True, []))

        (self.package / "article.md").write_text("# 题目\n\n又改了。\n", encoding="utf-8")
        ok, problems = review_gate.assess(self.package)
        self.assertFalse(ok)
        self.assertTrue(any("又发生变化" in item for item in problems))

    def test_source_change_makes_review_stale(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        self.record("continuity")
        self.record("reference")
        self.record("recheck")
        self.source.write_text("# 源稿\n\n新证据。\n", encoding="utf-8")
        ok, problems = review_gate.assess(self.package)
        self.assertFalse(ok)
        self.assertTrue(any("源稿" in item and "变化" in item for item in problems))

    def test_archived_report_change_makes_review_stale(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        self.record("continuity")
        self.record("reference")
        self.record("recheck")
        (self.package / "review/voice.md").write_text("已检查，PASS。\n", encoding="utf-8")
        ok, problems = review_gate.assess(self.package)
        self.assertFalse(ok)
        self.assertTrue(any("voice 报告" in item for item in problems))

    def test_recheck_cannot_precede_walkthroughs(self):
        self.init()
        report = self.root / "recheck.md"
        report.write_text(
            "## 范围\n\n已检查全文与所有改动接缝、上下文和事实边界。\n\n"
            "## 问题\n\n未发现阻断项，但此时尚未完成前置走查。\n\n"
            "## 结论\n\nPASS\n", encoding="utf-8")
        args = Namespace(package=self.package, check="recheck", verdict="PASS", report=report)
        with self.assertRaises(ValueError):
            review_gate.cmd_record(args)

    def test_recheck_requires_continuity(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        report = self.root / "recheck.md"
        report.write_text(
            "## 范围\n\n已检查全文与所有改动接缝、上下文和事实边界。\n\n"
            "## 问题\n\n未发现阻断项，但连续性走查尚未记录。\n\n"
            "## 结论\n\nPASS\n", encoding="utf-8")
        args = Namespace(package=self.package, check="recheck", verdict="PASS", report=report)
        with self.assertRaises(ValueError):
            review_gate.cmd_record(args)

    def test_recheck_requires_reference_walkthrough(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        self.record("continuity")
        report = self.root / "recheck.md"
        report.write_text(
            "## 范围\n\n已检查全文与所有改动接缝、相邻上下文、事实边界、链接和公开目录。\n\n"
            "## 问题\n\n指代可解性走查尚未记录，代号和简称是否能被普通读者理解仍未核验，当前不能完成复查。\n\n"
            "## 结论\n\nPASS\n", encoding="utf-8")
        args = Namespace(package=self.package, check="recheck", verdict="PASS", report=report)
        with self.assertRaisesRegex(ValueError, "reference"):
            review_gate.cmd_record(args)

    def test_walkthrough_recorded_after_recheck_invalidates_recheck(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        self.record("continuity")
        self.record("reference")
        self.record("recheck")

        self.record("reference")
        ok, problems = review_gate.assess(self.package)
        self.assertFalse(ok)
        self.assertIn("缺少 recheck 记录", problems)

    def test_one_line_pass_cannot_masquerade_as_report(self):
        self.init()
        report = self.root / "voice.md"
        report.write_text("已检查，PASS。\n", encoding="utf-8")
        args = Namespace(package=self.package, check="voice", verdict="PASS", report=report)
        with self.assertRaisesRegex(ValueError, "固定小节"):
            review_gate.cmd_record(args)

    def test_mechanical_has_separate_gate(self):
        self.init(mode="mechanical")
        self.record("mechanical")
        self.assertEqual(review_gate.assess(self.package), (True, []))
        manifest = json.loads((self.package / "review/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["checks"]), {"mechanical"})

    def test_single_markdown_target_goes_to_review_home(self):
        draft = self.root / "draft.md"
        draft.write_text("# 原创草稿\n", encoding="utf-8")
        args = Namespace(package=draft, lane="demo2", mode="editorial",
                         source=None, reset=False)
        self.assertEqual(review_gate.cmd_init(args), 0)
        records = list(self.review_home.glob("draft-*.review/manifest.json"))
        self.assertEqual(len(records), 1)
        # 目标项目（草稿所在目录）里不允许再出现 *.review/
        self.assertFalse((self.root / "draft.review").exists())

    def test_same_stem_in_different_directories_never_collides(self):
        for sub in ("a", "b"):
            (self.root / sub).mkdir()
            (self.root / sub / "draft.md").write_text("# 草稿\n", encoding="utf-8")
        for sub in ("a", "b"):
            args = Namespace(package=self.root / sub / "draft.md", lane="demo",
                             mode="editorial", source=None, reset=False)
            self.assertEqual(review_gate.cmd_init(args), 0)
        self.assertEqual(
            len(list(self.review_home.glob("draft-*.review/manifest.json"))), 2)

    def test_arbitrary_project_lane_is_supported(self):
        draft = self.root / "external-project.md"
        draft.write_text("# 外部项目文章\n", encoding="utf-8")
        args = Namespace(package=draft, lane="another-project", mode="editorial",
                         source=None, reset=False)
        self.assertEqual(review_gate.cmd_init(args), 0)
        (record,) = self.review_home.glob("external-project-*.review/manifest.json")
        manifest = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(manifest["lane"], "another-project")

    def test_voice_pass_is_blocked_when_paragraph_has_no_people(self):
        self.init()
        (self.package / "article.md").write_text(
            "# 题目\n\n编译器会在返回前检查保护值。\n", encoding="utf-8")
        report = self.root / "voice.md"
        report.write_text(
            "## 范围\n\n已逐段检查全文、每一个自然段的人称参与、相邻接缝和技术说明。\n\n"
            "## 问题\n\n审稿员声称没有发现声音问题，并准备把这份正文判为可以交付。\n\n"
            "## 结论\n\nPASS\n", encoding="utf-8")
        args = Namespace(package=self.package, check="voice", verdict="PASS", report=report)
        with self.assertRaisesRegex(ValueError, "Humanizer 未通过"):
            review_gate.cmd_record(args)

    def test_voice_pass_is_blocked_by_corner_quotes(self):
        self.init()
        (self.package / "article.md").write_text(
            "# 题目\n\n咱们把这一段私下叫作「第二阶段」。\n", encoding="utf-8")
        report = self.root / "voice.md"
        report.write_text(
            "## 范围\n\n已逐段检查全文、所有可见标点、临时概念、相邻接缝和技术说明。\n\n"
            "## 问题\n\n审稿员声称没有发现声音问题，并准备把这份正文判为可以交付。\n\n"
            "## 结论\n\nPASS\n", encoding="utf-8")
        args = Namespace(package=self.package, check="voice", verdict="PASS", report=report)
        with self.assertRaisesRegex(ValueError, "banned_corner_quotes"):
            review_gate.cmd_record(args)

    def test_balance_candidate_requires_quote_and_controller_review(self):
        self.init()
        original = "咱们动工不是写代码，是画地图。"
        (self.package / "article.md").write_text(
            f"# 题目\n\n{original}\n", encoding="utf-8")

        report = self.root / "voice.md"
        report.write_text(
            "## 范围\n\n已检查全文、对称结构、相邻上下文与作者面对读者的说话姿态。\n\n"
            "## 问题\n\n发现一处平衡句式，但报告没有按协议引用并升级给主控。\n\n"
            "## 结论\n\nCHANGES_REQUESTED\n", encoding="utf-8")
        args = Namespace(
            package=self.package, check="voice", verdict="CHANGES_REQUESTED", report=report)
        with self.assertRaisesRegex(ValueError, "平衡句式候选"):
            review_gate.cmd_record(args)

        report.write_text(
            "## 范围\n\n已检查全文、对称结构、相邻上下文与作者面对读者的说话姿态。\n\n"
            "## 问题\n\n**平衡句式候选｜主控二审**\n\n"
            f"> {original}\n\n"
            "否定半句是否有真实前提不能由走查员独自放行，现交主控二次评审。\n\n"
            "## 结论\n\nCHANGES_REQUESTED\n", encoding="utf-8")
        self.assertEqual(review_gate.cmd_record(args), 0)

        pass_args = Namespace(package=self.package, check="voice", verdict="PASS", report=report)
        report.write_text(report.read_text(encoding="utf-8").replace(
            "CHANGES_REQUESTED", "PASS"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "主控"):
            review_gate.cmd_record(pass_args)

        (self.package / "review/resolution.md").write_text(
            "# 问题处理\n\n**主控二审结论**\n\n"
            f"> {original}\n\n"
            "前文确实建立了读者可能误认的对象，主控决定保留这组真实对比。\n",
            encoding="utf-8")
        self.assertEqual(review_gate.cmd_record(pass_args), 0)

    def test_abstract_collocation_requires_quote_and_controller_review(self):
        self.init()
        original = "咱们不能让这层包装吞掉语义。"
        (self.package / "article.md").write_text(
            f"# 题目\n\n{original}\n", encoding="utf-8")

        report = self.root / "voice.md"
        report.write_text(
            "## 范围\n\n已检查全文的动词、抽象名词、相邻上下文与实际机制。\n\n"
            "## 问题\n\n发现一处用力的抽象动宾组合，但没有按协议升级。\n\n"
            "## 结论\n\nCHANGES_REQUESTED\n", encoding="utf-8")
        args = Namespace(
            package=self.package, check="voice", verdict="CHANGES_REQUESTED", report=report)
        with self.assertRaisesRegex(ValueError, "抽象动宾组合候选"):
            review_gate.cmd_record(args)

        report.write_text(
            "## 范围\n\n已检查全文的动词、抽象名词、相邻上下文与实际机制。\n\n"
            "## 问题\n\n**抽象动宾组合候选｜主控二审**\n\n"
            f"> {original}\n\n"
            "吞掉是否对应可观察机制不能由走查员独自放行，现交主控二审。\n\n"
            "## 结论\n\nCHANGES_REQUESTED\n", encoding="utf-8")
        self.assertEqual(review_gate.cmd_record(args), 0)

        pass_args = Namespace(package=self.package, check="voice", verdict="PASS", report=report)
        report.write_text(report.read_text(encoding="utf-8").replace(
            "CHANGES_REQUESTED", "PASS"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "抽象动宾组合二审结论"):
            review_gate.cmd_record(pass_args)

        (self.package / "review/resolution.md").write_text(
            "# 问题处理\n\n**抽象动宾组合二审结论**\n\n"
            f"> {original}\n\n"
            "这里具体指序列化后类型含义丢失，已有字段对照与输出作证，主控决定保留。\n",
            encoding="utf-8")
        self.assertEqual(review_gate.cmd_record(pass_args), 0)

    def test_ready_rechecks_humanizer_instead_of_trusting_reports(self):
        self.init()
        self.record("voice")
        self.record("fidelity")
        self.record("continuity")
        self.record("reference")
        self.record("recheck")
        (self.package / "article.md").write_text(
            "# 题目\n\n编译器会在返回前检查保护值。\n", encoding="utf-8")
        ok, problems = review_gate.assess(self.package)
        self.assertFalse(ok)
        self.assertTrue(any("paragraph_without_people" in item for item in problems))


if __name__ == "__main__":
    unittest.main()
