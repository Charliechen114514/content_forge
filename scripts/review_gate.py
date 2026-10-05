#!/usr/bin/env python3
"""content-forge 稿件复审门禁（纯标准库）。

用法:
  review_gate.py init TARGET --lane LANE --mode editorial|mechanical [--source FILE]
  review_gate.py record TARGET voice|fidelity|continuity|reference|recheck|mechanical PASS|CHANGES_REQUESTED --report FILE
  review_gate.py status TARGET
  review_gate.py ready TARGET

TARGET 可以是含 article.md 的发文包，也可以是单个 Markdown 草稿。
发文包的记录放在包内 review/；单文件的记录集中放在本机暂存区
（$CONTENT_FORGE_REVIEW_HOME，默认 /tmp/content_forge_review/），不写进目标项目。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_VERSION = 1
EDITORIAL_WALKTHROUGHS = ("voice", "fidelity", "continuity", "reference")
EDITORIAL_CHECKS = (*EDITORIAL_WALKTHROUGHS, "recheck")
VALID_CHECKS = (*EDITORIAL_CHECKS, "mechanical")
VALID_VERDICTS = ("PASS", "CHANGES_REQUESTED")
ROOT = Path(__file__).resolve().parent.parent
HUMANIZER = ROOT / "tools/humanizer_lint.py"
MANDATORY_REVIEW_PROTOCOLS = (
    {
        "rules": {"balance_not", "not_only"},
        "name": "平衡句式候选",
        "report_marker": "**平衡句式候选｜主控二审**",
        "decision_marker": "**主控二审结论**",
    },
    {
        "rules": {"abstract_force_collocation"},
        "name": "抽象动宾组合候选",
        "report_marker": "**抽象动宾组合候选｜主控二审**",
        "decision_marker": "**抽象动宾组合二审结论**",
    },
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def review_root() -> Path:
    """单文件复审记录的集中存放处，可用 CONTENT_FORGE_REVIEW_HOME 覆盖。"""
    return Path(os.environ.get("CONTENT_FORGE_REVIEW_HOME", "/tmp/content_forge_review"))


def paths(target: Path) -> tuple[Path, Path, Path]:
    if target.is_file() or target.suffix.lower() == ".md":
        article = target.resolve()
        # 目录名带文章绝对路径的短哈希：同名文章不撞车，目标项目里也不再拉出 *.review/
        stamp = hashlib.sha256(str(article).encode("utf-8")).hexdigest()[:8]
        review_dir = review_root() / f"{target.stem}-{stamp}.review"
        return article, review_dir, review_dir / "manifest.json"
    return target / "article.md", target / "review", target / "review" / "manifest.json"


def load_manifest(package: Path) -> dict:
    _, _, manifest_path = paths(package)
    if not manifest_path.is_file():
        raise ValueError(f"缺少 {manifest_path}，先执行 init")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 manifest: {exc}") from exc
    if data.get("version") != MANIFEST_VERSION:
        raise ValueError(f"不支持的 manifest 版本: {data.get('version')}")
    return data


def save_manifest(package: Path, data: dict) -> None:
    _, review_dir, manifest_path = paths(package)
    review_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_source(raw: str | None) -> Path | None:
    return Path(raw).expanduser().resolve() if raw else None


def humanizer_findings(article: Path) -> list[dict]:
    """运行 Humanizer，并返回硬错误与需主控二审的候选。"""
    result = subprocess.run(
        [sys.executable, str(HUMANIZER), "--format", "json", str(article)],
        capture_output=True, text=True, cwd=ROOT)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        detail = (result.stderr or result.stdout).strip() or "执行失败"
        return [{
            "level": "error",
            "rule": "runtime_failure",
            "line": 1,
            "message": f"Humanizer 无法完成检查: {detail}",
        }]


def humanizer_problems(article: Path) -> list[str]:
    """只把硬错误送进 READY 阻断；review 候选由报告与主控二审处理。"""
    findings = humanizer_findings(article)
    return [
        f"Humanizer {item['rule']} @ line {item['line']}: {item['message']}"
        for item in findings if item.get("level") == "error"
    ]


def finding_sentence(lines: list[str], item: dict) -> str:
    """取命中所在的完整句子，避免要求报告引用整段 Markdown 原行。"""
    line_no = int(item["line"])
    line = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else ""
    hit = str(item.get("hit", "")).rstrip("…")
    position = line.find(hit)
    if not line or position < 0:
        return line

    start = max(line.rfind(mark, 0, position) for mark in "。！？!?") + 1
    ends = [line.find(mark, position + len(hit)) for mark in "。！？!?"
            if line.find(mark, position + len(hit)) >= 0]
    end = min(ends) + 1 if ends else len(line)
    return line[start:end].strip()


def validate_mandatory_reviews(
        article: Path, review_dir: Path, body: str, verdict: str) -> None:
    """所有 review 级候选都必须逐句引用并显式升级，不能被静默吞掉。"""
    all_findings = humanizer_findings(article)
    lines = article.read_text(encoding="utf-8").splitlines()

    for protocol in MANDATORY_REVIEW_PROTOCOLS:
        findings = [item for item in all_findings if item.get("rule") in protocol["rules"]]
        if not findings:
            continue
        name = str(protocol["name"])
        report_marker = str(protocol["report_marker"])
        decision_marker = str(protocol["decision_marker"])
        if report_marker not in body:
            raise ValueError(f"{name}必须使用标记 {report_marker} 交主控二审")

        missing_quotes: list[int] = []
        for item in findings:
            line_no = int(item["line"])
            original = finding_sentence(lines, item)
            if original and f"> {original}" not in body:
                missing_quotes.append(line_no)
        if missing_quotes:
            rendered = ", ".join(str(line) for line in sorted(set(missing_quotes)))
            raise ValueError(f"{name}必须用 Markdown 引用完整原句，缺少行: {rendered}")

        if verdict != "PASS":
            continue
        resolution = review_dir / "resolution.md"
        resolution_body = resolution.read_text(encoding="utf-8") if resolution.is_file() else ""
        if decision_marker not in resolution_body:
            raise ValueError(
                f"{name}仍保留时，主控必须在 resolution.md 写入 {decision_marker}"
            )
        missing_decisions: list[int] = []
        for item in findings:
            line_no = int(item["line"])
            original = finding_sentence(lines, item)
            if original and f"> {original}" not in resolution_body:
                missing_decisions.append(line_no)
        if missing_decisions:
            rendered = ", ".join(str(line) for line in sorted(set(missing_decisions)))
            raise ValueError(f"{name}的主控二审结论必须再次引用原句，缺少行: {rendered}")


def validate_report(body: str, verdict: str) -> None:
    """防止用一句「已检查，PASS」代替真正走查。"""
    compact = re.sub(r"\s+", "", body)
    required = ("## 范围", "## 问题", "## 结论")
    missing = [heading for heading in required if heading not in body]
    if missing:
        raise ValueError(f"报告缺少固定小节: {', '.join(missing)}")
    if len(compact) < 60:
        raise ValueError("报告过短；必须写明实际走查范围、问题与结论")
    conclusion = body.split("## 结论", 1)[1]
    if verdict not in conclusion:
        raise ValueError(f"报告的「## 结论」小节未写明 {verdict}")


def cmd_init(args: argparse.Namespace) -> int:
    package = args.package.resolve()
    article, review_dir, manifest_path = paths(package)
    if not article.is_file():
        raise ValueError(f"缺少正文: {article}")
    if manifest_path.exists() and not args.reset:
        raise ValueError(f"{manifest_path} 已存在；要废弃旧复审记录时显式使用 --reset")

    source = resolve_source(args.source)
    if source and not source.is_file():
        raise ValueError(f"源稿不存在: {source}")
    if review_dir.exists() and args.reset:
        shutil.rmtree(review_dir)

    data = {
        "version": MANIFEST_VERSION,
        "lane": args.lane,
        "mode": args.mode,
        "article": str(article),
        "source": str(source) if source else None,
        "sourceSha256": digest(source) if source else None,
        "initializedArticleSha256": digest(article),
        "initializedAt": now(),
        "checks": {},
    }
    save_manifest(package, data)
    print(f"✓ 复审单已建立: {manifest_path}")
    print(f"  lane={args.lane} mode={args.mode}")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    package = args.package.resolve()
    article, review_dir, _ = paths(package)
    data = load_manifest(package)
    if not article.is_file():
        raise ValueError(f"缺少正文: {article}")

    expected = set(EDITORIAL_CHECKS if data["mode"] == "editorial" else ("mechanical",))
    if args.check not in expected:
        raise ValueError(f"mode={data['mode']} 不接受 {args.check} 检查")
    report = args.report.resolve()
    if not report.is_file() or not report.read_text(encoding="utf-8").strip():
        raise ValueError(f"报告不存在或为空: {report}")
    body = report.read_text(encoding="utf-8").rstrip() + "\n"
    validate_report(body, args.verdict)

    if data["mode"] == "editorial" and args.check == "voice":
        validate_mandatory_reviews(article, review_dir, body, args.verdict)

    if data["mode"] == "editorial" and args.verdict == "PASS" and args.check in {"voice", "recheck"}:
        lint_problems = humanizer_problems(article)
        if lint_problems:
            preview = "\n".join(f"- {item}" for item in lint_problems[:12])
            if len(lint_problems) > 12:
                preview += f"\n- 其余 {len(lint_problems) - 12} 项"
            raise ValueError(f"Humanizer 未通过，不能记录 {args.check}=PASS:\n{preview}")

    checks = data.setdefault("checks", {})
    if args.check == "recheck":
        missing = [name for name in EDITORIAL_WALKTHROUGHS
                   if checks.get(name, {}).get("verdict") != "PASS"]
        if missing:
            raise ValueError(f"recheck 之前必须先记录 PASS: {', '.join(missing)}")
        resolution = review_dir / "resolution.md"
        if not resolution.is_file() or not resolution.read_text(encoding="utf-8").strip():
            raise ValueError(f"recheck 之前必须填写非空的 {review_dir / 'resolution.md'}")
    elif args.check in EDITORIAL_WALKTHROUGHS:
        # 新增或重录任一走查，都说明旧的总复查没有覆盖当前证据。
        # 这也让新增门禁能够安全接管旧 manifest：补 reference 后必须再做 recheck。
        checks.pop("recheck", None)

    review_dir.mkdir(parents=True, exist_ok=True)
    destination = review_dir / f"{args.check}.md"
    destination.write_text(body, encoding="utf-8")
    checks[args.check] = {
        "verdict": args.verdict,
        "articleSha256": digest(article),
        "recordedAt": now(),
        "report": destination.name,
        "reportSha256": digest(destination),
    }
    if args.check == "recheck":
        checks[args.check]["resolutionSha256"] = digest(review_dir / "resolution.md")
    save_manifest(package, data)
    print(f"✓ {args.check}: {args.verdict} → {destination}")
    return 0


def assess(package: Path) -> tuple[bool, list[str]]:
    package = package.resolve()
    article, review_dir, _ = paths(package)
    data = load_manifest(package)
    problems: list[str] = []
    if not article.is_file():
        return False, [f"缺少正文: {article}"]

    source_raw = data.get("source")
    if source_raw:
        source = Path(source_raw)
        if not source.is_file():
            problems.append(f"源稿已不存在: {source}")
        elif digest(source) != data.get("sourceSha256"):
            problems.append("源稿在 intake 后发生变化，需重新 init 并复审")

    checks = data.get("checks", {})
    required = EDITORIAL_CHECKS if data.get("mode") == "editorial" else ("mechanical",)
    current_hash = digest(article)
    for name in required:
        item = checks.get(name)
        if not item:
            problems.append(f"缺少 {name} 记录")
            continue
        if item.get("verdict") != "PASS":
            problems.append(f"{name} 尚未通过: {item.get('verdict', 'UNKNOWN')}")
        report = review_dir / str(item.get("report", ""))
        if not report.is_file() or not report.read_text(encoding="utf-8").strip():
            problems.append(f"{name} 报告缺失或为空")
            continue
        report_body = report.read_text(encoding="utf-8")
        try:
            validate_report(report_body, item.get("verdict", ""))
        except ValueError as exc:
            problems.append(f"{name} 报告格式无效: {exc}")
        if digest(report) != item.get("reportSha256"):
            problems.append(f"{name} 报告在归档后又发生变化")

    final_check = "recheck" if data.get("mode") == "editorial" else "mechanical"
    final_item = checks.get(final_check, {})
    if final_item and final_item.get("articleSha256") != current_hash:
        problems.append(f"article.md 在 {final_check} 后又发生变化")
    if data.get("mode") == "editorial" and final_item:
        resolution = review_dir / "resolution.md"
        if not resolution.is_file() or not resolution.read_text(encoding="utf-8").strip():
            problems.append("resolution.md 缺失或为空")
        elif digest(resolution) != final_item.get("resolutionSha256"):
            problems.append("resolution.md 在 recheck 后又发生变化")
    if data.get("mode") == "editorial":
        problems.extend(humanizer_problems(article))
    return not problems, problems


def cmd_status(args: argparse.Namespace, strict: bool) -> int:
    ok, problems = assess(args.package)
    print(f"{'READY' if ok else 'NOT_READY'}  {args.package.resolve()}")
    for problem in problems:
        print(f"  - {problem}")
    return 0 if ok else (1 if strict else 0)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    subs = root.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init")
    init.add_argument("package", type=Path)
    init.add_argument("--lane", required=True)
    init.add_argument("--mode", choices=("editorial", "mechanical"), required=True)
    init.add_argument("--source")
    init.add_argument("--reset", action="store_true")

    record = subs.add_parser("record")
    record.add_argument("package", type=Path)
    record.add_argument("check", choices=VALID_CHECKS)
    record.add_argument("verdict", choices=VALID_VERDICTS)
    record.add_argument("--report", required=True, type=Path)

    for name in ("status", "ready"):
        sub = subs.add_parser(name)
        sub.add_argument("package", type=Path)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "record":
            return cmd_record(args)
        return cmd_status(args, strict=args.command == "ready")
    except (OSError, ValueError, KeyError) as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
