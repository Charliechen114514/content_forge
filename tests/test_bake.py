"""Unit tests for tools/bake.py. Pure stdlib: python3 -m unittest discover -s tests

临时目录搭最小骨架,不读真仓:doctor 的 unittest discover 在任何机器都得绿。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import bake  # noqa: E402


def make_repo(root):
    root = Path(root)
    for d in ("recipes/base", "recipes/process", "recipes/review",
              "recipes/voice", "recipes/scenes", "recipes/roles",
              "tools/humanizer-zh/corpus", "combos"):
        (root / d).mkdir(parents=True, exist_ok=True)
    cards = {
        "recipes/base/forge-base.md":
            "# 基座:平台宪法(forge-base)\n\n规则一。\n\n```lint\nbanned ## 1 ## error\n```\n\n## 来源\n\n出处注记。\n",
        "recipes/process/five-gates.md": "# 流程:五道关(five-gates)\n\n流程条款。\n",
        "recipes/process/mechanical.md": "# 流程:机械模式(mechanical)\n\n机械条款。\n",
        "recipes/review/writing-style.md": "# 审稿:技术线写作规约(writing-style)\n\n判据条款。\n",
        "recipes/voice/author-tech.md": "# 声音:技术线作者声音(author-tech)\n\n声音条款。\n",
        "recipes/scenes/tech-blog.md": "# 场景:技术博文(tech-blog)\n\n场景条款。\n",
        "recipes/roles/master.md": "# 角色:主控调度(master)\n\n主控条款。\n",
        "recipes/roles/writer.md": "# 角色:技术线写手(writer)\n\n写手条款。\n",
        "recipes/roles/voice-walker.md": "# 角色:声音走查员(voice-walker)\n\n声音走查条款。\n",
        "recipes/roles/fidelity-walker.md": "# 角色:内容保真走查员(fidelity-walker)\n\n保真条款。\n",
        "recipes/roles/thread-walker.md": "# 角色:连续性走查员(thread-walker)\n\n连续性条款。\n",
        "recipes/roles/reference-walker.md": "# 角色:指代可解性走查员(reference-walker)\n\n指代条款。\n",
    }
    for rel, text in cards.items():
        (root / rel).write_text(text, encoding="utf-8")
    # 语料里故意放一个「## 来源」节,证明语料不走剥除逻辑
    (root / "tools/humanizer-zh/corpus/VOICE.md").write_text(
        "声音正文。\n\n## 来源\n\n语料里的来源必须保留。\n", encoding="utf-8")
    (root / "tools/humanizer-zh/corpus/COMPARE.md").write_text("工作坊正文。\n", encoding="utf-8")
    (root / "tools/humanizer-zh/corpus/approved.toml").write_text("[样本]\n", encoding="utf-8")
    return root


COMBO = {
    "lane": "t",
    "base": "forge-base",
    "process": ["five-gates", "mechanical"],
    "review": ["writing-style"],
    "voice": "author-tech",
    "scene": "tech-blog",
    "roles": ["master", "writer", "voice-walker", "fidelity-walker",
              "thread-walker", "reference-walker"],
}


def write_combo(root, combo):
    p = root / "combos/t.json"
    p.write_text(json.dumps(combo, ensure_ascii=False), encoding="utf-8")
    return p


class Resolve(unittest.TestCase):
    def test_layers_in_canonical_order_base_first(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            layers, roles = bake.resolve(COMBO, repo=root)
            self.assertEqual(layers[0][0], "base")
            self.assertEqual([l[0] for l in layers],
                             ["base", "process", "process", "review", "voice", "scene"])
            self.assertEqual(len(roles), 6)

    def test_missing_layer_is_hard_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            with self.assertRaises(ValueError) as ctx:
                bake.resolve(dict(COMBO, review=["ghost"]), repo=root)
            self.assertIn("不存在", str(ctx.exception))

    def test_base_must_be_single_value(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            with self.assertRaises(ValueError) as ctx:
                bake.resolve(dict(COMBO, base=["a", "b"]), repo=root)
            self.assertIn("单值", str(ctx.exception))

    def test_unknown_combo_key_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            with self.assertRaises(ValueError) as ctx:
                bake.resolve(dict(COMBO, tones={"rhythm": "mixed"}), repo=root)
            self.assertIn("未知清单字段", str(ctx.exception))

    def test_unknown_role_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            with self.assertRaises(ValueError) as ctx:
                bake.resolve(dict(COMBO, roles=["butler"]), repo=root)
            self.assertIn("未知角色", str(ctx.exception))


class BakeAndCheck(unittest.TestCase):
    def test_writer_pack_full_and_corpus_verbatim(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            s = bake.bake_combo(root, write_combo(root, COMBO))
            self.assertEqual(len(s["packs"]), 6)
            pack = (root / "build/t/writer.md").read_text(encoding="utf-8")
            self.assertIn("由 tools/bake.py 生成", pack)
            self.assertIn("路由:", pack)
            self.assertIn(bake.PRIORITY_LINE, pack)
            self.assertIn("combo:", pack)
            self.assertIn("语料指纹:", pack)
            self.assertIn("规则一。", pack)                # 层卡全文内联
            self.assertIn(bake.LINT_PLACEHOLDER, pack)     # lint 块剥除
            self.assertNotIn("banned ## 1", pack)
            self.assertNotIn("出处注记", pack)              # 来源节剥除
            self.assertIn("写手条款。", pack)                # 角色卡在内
            self.assertIn("<!-- corpus:COMPARE.md -->", pack)
            self.assertIn("工作坊正文。", pack)
            self.assertIn("语料里的来源必须保留。", pack)    # 语料永不剥除
            self.assertIn("场景条款。", pack)                # 场景层进写手包
            self.assertNotIn("判据条款。", pack)             # 写手禁审稿层
            self.assertNotIn("流程条款。", pack)             # 写手禁流程层

    def test_role_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            bake.bake_combo(root, write_combo(root, COMBO))
            fidelity = (root / "build/t/fidelity-walker.md").read_text(encoding="utf-8")
            self.assertIn("保真条款。", fidelity)
            self.assertIn("场景条款。", fidelity)            # 场景层随走查包
            self.assertNotIn("工作坊正文。", fidelity)       # 保真不读语料
            self.assertIn("本角色不读语料", fidelity)
            master = (root / "build/t/master.md").read_text(encoding="utf-8")
            self.assertIn("判据条款。", master)              # 主控读审稿层
            self.assertNotIn("工作坊正文。", master)         # 主控包不带语料
            voice = (root / "build/t/voice-walker.md").read_text(encoding="utf-8")
            self.assertIn("声音走查条款。", voice)
            self.assertIn("工作坊正文。", voice)             # 声音走查带语料

    def test_check_three_states_and_reflow(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            cp = write_combo(root, COMBO)
            self.assertEqual(bake.check_combo(root, cp)[0], "missing")   # 未烘焙不算错
            bake.bake_combo(root, cp)
            self.assertEqual(bake.check_combo(root, cp)[0], "ok")
            (root / "build/t/writer.md").write_text("被手改了\n", encoding="utf-8")
            status, notes = bake.check_combo(root, cp)
            self.assertEqual(status, "drift")
            self.assertIn("writer.md", notes)
            bake.bake_combo(root, cp)
            (root / "recipes/base/forge-base.md").write_text(
                "# 基座:平台宪法(forge-base)\n\n规则二。\n", encoding="utf-8")
            self.assertEqual(bake.check_combo(root, cp)[0], "drift")     # 正本改动,全部包漂移

    def test_fatal_path_fails_bake(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            (root / "recipes/voice/author-tech.md").write_text(
                "# 声音:技术线作者声音(author-tech)\n\n看 /home/who/secret。\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                bake.bake_combo(root, write_combo(root, COMBO))
            self.assertIn("泄漏", str(ctx.exception))

    def test_no_voice_means_no_corpus(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            combo = dict(COMBO, voice=None, roles=["master", "fidelity-walker"])
            bake.bake_combo(root, write_combo(root, combo))
            for r in ("master", "fidelity-walker"):
                pack = (root / f"build/t/{r}.md").read_text(encoding="utf-8")
                self.assertNotIn("<!-- corpus:", pack)

    def test_role_layer_extras_append(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            combo = dict(COMBO, roles=["voice-walker"],
                         role_layer_extras={"voice-walker": ["review"]})
            bake.bake_combo(root, write_combo(root, combo))
            pack = (root / "build/t/voice-walker.md").read_text(encoding="utf-8")
            self.assertIn("判据条款。", pack)                # 加装的审稿层进了包

    def test_digest_changes_with_layer_content(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(d)
            layers, roles = bake.resolve(COMBO, repo=root)
            d1 = bake.combo_digest(COMBO, layers, roles, root)
            (root / "recipes/base/forge-base.md").write_text(
                "# 基座:平台宪法(forge-base)\n\n规则一改。\n", encoding="utf-8")
            layers, roles = bake.resolve(COMBO, repo=root)
            d2 = bake.combo_digest(COMBO, layers, roles, root)
            self.assertNotEqual(d1, d2)


if __name__ == "__main__":
    unittest.main()
