#!/usr/bin/env python3
"""content-forge 环境体检。

逐项 OK/INFO/FAIL:python 解释器 / 通用角色薄壳与语料 / 工作坊完整性 / 复审回归 / 层卡清单 / 烘焙一致性。
任一 FAIL → exit 1。平台纯标准库,不检查任何 venv 或第三方依赖。

用法:
  python3 scripts/doctor.py          # 全量
  python3 scripts/doctor.py --quiet  # 只打印非 OK 项
"""
import sys, subprocess, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fails, infos = [], []


def check(label, ok, level, detail=""):
    flag = {"OK": "✓", "INFO": "·", "FAIL": "✗"}[level]
    if level == "FAIL":
        fails.append(label)
    elif level == "INFO":
        infos.append(label)
    if level == "OK" and "--quiet" in sys.argv:
        return
    print(f"  {flag} {label}" + (f" — {detail}" if detail else ""))


def main():
    print("content-forge 体检")
    # python 解释器
    has = shutil.which("python3") is not None
    check("python3 存在", has, "OK" if has else "FAIL", "" if has else "缺失")

    # 任意项目接入所需的五张角色薄壳与语料正本
    generic_assets = (
        ROOT / ".claude/agents/content-writer.md",
        ROOT / ".claude/agents/content-voice-walker.md",
        ROOT / ".claude/agents/content-fidelity-reviewer.md",
        ROOT / ".claude/agents/content-thread-walker.md",
        ROOT / ".claude/agents/content-reference-walker.md",
        ROOT / "tools/humanizer-zh/corpus/VOICE.md",
        ROOT / "tools/humanizer-zh/corpus/COMPARE.md",
    )
    missing_assets = [str(path.relative_to(ROOT)) for path in generic_assets if not path.is_file()]
    check("通用角色薄壳与语料", not missing_assets, "OK" if not missing_assets else "FAIL",
          "" if not missing_assets else f"缺失: {', '.join(missing_assets)}")

    corpus_files = [ROOT / f"tools/humanizer-zh/corpus/{n}"
                    for n in ("VOICE.md", "COMPARE.md", "approved.toml")]
    missing_corpus = [p.name for p in corpus_files if not p.is_file()]
    workshop = ROOT / "tools/humanizer-zh/corpus/COMPARE.md"
    workshop_text = workshop.read_text(encoding="utf-8") if workshop.is_file() else ""
    full_corpus = (not missing_corpus
                   and len(workshop_text.encode("utf-8")) >= 40_000)
    if missing_corpus:
        check("作者语料", False, "FAIL", f"缺失: {', '.join(missing_corpus)}")
    else:
        check("作者语料", full_corpus, "OK" if full_corpus else "INFO",
              "" if full_corpus else "示例语料(体量不足 40k),换入自有成对改稿后本项转 OK")

    # 平台级复审门禁回归（纯标准库，不读写真实稿件）
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-q"],
        capture_output=True, text=True, cwd=ROOT)
    check("编辑复审门禁回归", r.returncode == 0, "OK" if r.returncode == 0 else "FAIL",
          "" if r.returncode == 0 else "执行失败")

    # 层卡正本与选层清单
    recipes_assets = [ROOT / p for p in (
        "recipes/base/forge-base.md",
        "recipes/process/five-gates.md",
        "recipes/process/mechanical.md",
        "recipes/review/writing-style.md",
        "recipes/voice/author-tech.md",
        "recipes/roles/master.md",
        "recipes/roles/writer.md",
        "recipes/roles/voice-walker.md",
        "recipes/roles/fidelity-walker.md",
        "recipes/roles/thread-walker.md",
        "recipes/roles/reference-walker.md",
        "combos/single-editorial.json",
    )]
    missing_recipes = [str(p.relative_to(ROOT)) for p in recipes_assets if not p.is_file()]
    check("层卡正本与选层清单", not missing_recipes,
          "OK" if not missing_recipes else "FAIL",
          "" if not missing_recipes else f"缺失: {', '.join(missing_recipes)}")

    # 烘焙产物一致性(尚未烘焙只提示,不算失败)
    if not (ROOT / "build").is_dir():
        check("烘焙产物一致性", True, "INFO", "尚未烘焙,跑 workchop bake 生成角色包")
    else:
        r = subprocess.run([sys.executable, str(ROOT / "tools/bake.py"), "--check"],
                           capture_output=True, text=True, cwd=ROOT)
        check("烘焙产物一致性", r.returncode == 0,
              "OK" if r.returncode == 0 else "FAIL",
              "" if r.returncode == 0 else "产物与正本漂移,重跑 workchop bake")

    print(f"\n结果: {len(fails)} FAIL / {len(infos)} INFO")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
