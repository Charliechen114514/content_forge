#!/usr/bin/env python3
"""Humanizer-ZH: 面向中文技术文章的可校准文风检查器。

规则、作用域与回归样本放在同目录 humanizer-zh/ 下。执行器只负责解析
Markdown、运行声明式规则和稳定输出；它不判断文章是不是 AI 写的，也不
自动重写正文。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).with_name("humanizer-zh")
LEVEL_ORDER = {"error": 1, "review": 0}


@dataclass(frozen=True)
class Segment:
    scope: str
    line: int
    text: str


@dataclass(frozen=True)
class Rule:
    id: str
    level: str
    check: str
    scope: str
    message: str
    patterns: tuple[re.Pattern[str], ...]
    limit: int | None = None


@dataclass(frozen=True)
class Finding:
    level: str
    source: str
    line: int
    rule_id: str
    hit: str
    message: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "level": self.level,
            "source": self.source,
            "line": self.line,
            "rule": self.rule_id,
            "hit": self.hit,
            "message": self.message,
        }


def _read_toml(path: Path) -> dict:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def load_rules(root: Path = ROOT) -> list[Rule]:
    """Load and validate every declarative rule in deterministic order."""
    rules: list[Rule] = []
    seen: set[str] = set()
    for path in sorted((root / "rules").glob("*.toml")):
        for raw in _read_toml(path).get("rules", []):
            rule_id = raw["id"]
            if rule_id in seen:
                raise ValueError(f"duplicate rule id: {rule_id}")
            seen.add(rule_id)
            level = raw.get("level", "warn")
            check = raw.get("check", "existence")
            scope = raw.get("scope", "prose")
            if level not in LEVEL_ORDER:
                raise ValueError(f"{rule_id}: unknown level {level}")
            if check not in {"existence", "absence", "active_person", "occurrence", "clause_warmth"}:
                raise ValueError(f"{rule_id}: unknown check {check}")
            if scope not in {
                "prose",
                "visible",
                "visible_raw",
                "reader_visible",
                "list_item",
                "paragraph",
                "heading",
                "code_block",
                "document",
            }:
                raise ValueError(f"{rule_id}: unknown scope {scope}")
            patterns = tuple(re.compile(item, re.MULTILINE) for item in raw["patterns"])
            rules.append(
                Rule(
                    id=rule_id,
                    level=level,
                    check=check,
                    scope=scope,
                    message=raw["message"],
                    patterns=patterns,
                    limit=raw.get("limit"),
                )
            )
    if not rules:
        raise ValueError(f"no rules found under {root / 'rules'}")
    return rules


def _strip_inline_code(text: str) -> str:
    return re.sub(r"`[^`]*`", "", text)


def _strip_md_links(text: str) -> str:
    """行内 Markdown 链接只留锚文字；URL 是机器路径不是给读者读的散文。"""
    return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)


def _strip_inline_components(text: str) -> str:
    """行内 Vue/HTML 组件标签（含属性）整段剥掉，标签之间的读者可见文字保留；
    行首开头的多行组件块已由 HTML 块跳过逻辑处理。"""
    return re.sub(r"</?[A-Za-z][^<>]*>", "", text)


def _strip_prose_noise(text: str) -> str:
    return _strip_inline_components(_strip_md_links(_strip_inline_code(text)))


def parse_markdown(text: str) -> list[Segment]:
    """Extract useful Markdown scopes without pulling in an AST dependency."""
    segments: list[Segment] = []
    paragraph: list[str] = []
    paragraph_line = 0
    code: list[str] = []
    code_line = 0
    in_code = False
    in_html = False
    in_frontmatter = False
    frontmatter_closed = False
    in_promo = False
    document_parts: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph, paragraph_line
        if paragraph:
            segments.append(Segment("paragraph", paragraph_line, "\n".join(paragraph)))
        paragraph = []
        paragraph_line = 0

    def flush_code() -> None:
        nonlocal code, code_line
        if code:
            segments.append(Segment("code_block", code_line, "\n".join(code)))
        code = []
        code_line = 0

    for line_no, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        left = raw_line.lstrip()

        if line_no == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
                frontmatter_closed = True
            continue
        if not frontmatter_closed and line_no > 1:
            frontmatter_closed = True

        if left.startswith("<!-- promo:"):
            flush_paragraph()
            in_promo = True
            continue
        if left.startswith("<!-- /promo"):
            in_promo = False
            continue
        if in_promo:
            continue

        # 块引用内嵌的围栏代码块（"> ```c"）也是代码，先剥掉引用标记再判围栏，
        # 否则块引用里的代码会被当散文扫出 clause_without_warmth 误报
        fence_candidate = re.sub(r"^\s*>\s?", "", raw_line)
        if fence_candidate.startswith("```") or fence_candidate.startswith("~~~"):
            flush_paragraph()
            if in_code:
                flush_code()
            else:
                code_line = line_no + 1
            in_code = not in_code
            continue
        if in_code:
            code.append(raw_line)
            continue

        if in_html:
            # CommonMark HTML 块：行首 < 开启，延续到首个空行为止
            # （组件属性行不是散文，不参与 prose/visible 扫描）
            if not stripped:
                in_html = False
            continue

        if not stripped:
            flush_paragraph()
            continue
        if left.startswith("#"):
            flush_paragraph()
            heading = re.sub(r"^#{1,6}\s*", "", left)
            segments.append(Segment("heading", line_no, _strip_prose_noise(heading)))
            segments.append(Segment("visible", line_no, _strip_prose_noise(heading)))
            segments.append(Segment("visible_raw", line_no, _strip_inline_components(heading)))
            segments.append(Segment("reader_visible", line_no, _strip_prose_noise(heading)))
            document_parts.append(heading)
            continue
        # 独占一行的图片（含块引用内嵌的）是图面元数据不是散文：alt 与 drawio
        # 内容一一对应，还可能进 @dhlx 的 title 模板，不参与扫描；
        # 行内混排的图片（前后还有散文）仍按散文扫
        img_candidate = re.sub(r"^\s*>\s?", "", raw_line).strip()
        if re.match(r"^!\[[^\]]*\]\([^)]*\)$", img_candidate):
            flush_paragraph()
            continue
        if left.startswith("|"):
            flush_paragraph()
            segments.append(Segment("reader_visible", line_no, _strip_prose_noise(raw_line)))
            continue
        if left.startswith(("---", ":::", "<", "  //", "    //")):
            flush_paragraph()
            if left.startswith("<"):
                in_html = True
            continue

        raw_visible = _strip_inline_components(re.sub(r"^\s*>\s?", "", raw_line))
        visible = _strip_prose_noise(raw_visible)
        list_match = re.match(r"^\s*(?:[-*+] |\d+[.)]\s+)(.*)$", visible)
        if list_match:
            flush_paragraph()
            segments.append(Segment("list_item", line_no, list_match.group(1)))
            segments.append(Segment("visible", line_no, list_match.group(1)))
            segments.append(Segment("reader_visible", line_no, list_match.group(1)))
            raw_list_match = re.match(r"^\s*(?:[-*+] |\d+[.)]\s+)(.*)$", raw_visible)
            segments.append(
                Segment("visible_raw", line_no, raw_list_match.group(1) if raw_list_match else raw_visible)
            )
            document_parts.append(list_match.group(1))
            continue

        segments.append(Segment("prose", line_no, visible))
        segments.append(Segment("visible", line_no, visible))
        segments.append(Segment("visible_raw", line_no, raw_visible))
        segments.append(Segment("reader_visible", line_no, visible))
        document_parts.append(visible)
        if not paragraph:
            paragraph_line = line_no
        paragraph.append(visible)

    flush_paragraph()
    if in_code:
        flush_code()
    segments.append(Segment("document", 1, "\n".join(document_parts)))
    return segments


def _short_hit(text: str, size: int = 28) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= size else compact[:size] + "…"


def lint_text(text: str, source: str, rules: Iterable[Rule] | None = None) -> list[Finding]:
    active_rules = list(rules) if rules is not None else load_rules()
    by_scope: dict[str, list[Segment]] = {}
    for segment in parse_markdown(text):
        by_scope.setdefault(segment.scope, []).append(segment)

    findings: list[Finding] = []
    for rule in active_rules:
        targets = by_scope.get(rule.scope, [])
        if rule.check == "existence":
            for segment in targets:
                match = next((m for pattern in rule.patterns if (m := pattern.search(segment.text))), None)
                if match:
                    findings.append(
                        Finding(rule.level, source, segment.line, rule.id, _short_hit(match.group(0)), rule.message)
                    )
            continue

        if rule.check == "absence":
            for segment in targets:
                if not any(pattern.search(segment.text) for pattern in rule.patterns):
                    findings.append(
                        Finding(rule.level, source, segment.line, rule.id,
                                "整段未出现", rule.message)
                    )
            continue

        if rule.check == "active_person":
            for segment in targets:
                matches = [match for pattern in rule.patterns for match in pattern.finditer(segment.text)]
                only_possessive = bool(matches) and all(
                    match.end() < len(segment.text) and segment.text[match.end()] == "的"
                    for match in matches
                )
                if not matches or only_possessive:
                    findings.append(
                        Finding(rule.level, source, segment.line, rule.id,
                                "整段未出现" if not matches else "人称仅作所有格",
                                rule.message)
                    )
            continue

        if rule.check == "clause_warmth":
            quoted = re.compile(r'“[^”]*”|"[^"]*"|‘[^’]*’|『[^』]*』|「[^」]*」')
            for segment in targets:
                for clause in re.split(r"[,，。]+", quoted.sub("，", segment.text)):
                    clause = clause.strip()
                    if clause and not any(
                        pattern.search(clause) for pattern in rule.patterns
                    ):
                        findings.append(
                            Finding(rule.level, source, segment.line, rule.id,
                                    _short_hit(clause), rule.message)
                        )
            continue

        for segment in targets:
            matches: list[re.Match[str]] = []
            for pattern in rule.patterns:
                matches.extend(pattern.finditer(segment.text))
            limit = rule.limit if rule.limit is not None else 0
            if len(matches) > limit:
                findings.append(
                    Finding(rule.level, source, segment.line, rule.id, f"共 {len(matches)} 处", rule.message)
                )

    return sorted(findings, key=lambda item: (item.source, item.line, -LEVEL_ORDER[item.level], item.rule_id))


def run_self_tests(root: Path = ROOT) -> int:
    rules = load_rules(root)
    cases = _read_toml(root / "tests" / "cases.toml").get("cases", [])
    failures: list[str] = []
    for case in cases:
        found = {item.rule_id for item in lint_text(case["text"], case["name"], rules)}
        expected = set(case.get("expect", []))
        forbidden = set(case.get("forbid", []))
        if case.get("clean") and found:
            failures.append(f"{case['name']}: expected clean, got {sorted(found)}")
        missing = expected - found
        leaked = forbidden & found
        if missing:
            failures.append(f"{case['name']}: missing {sorted(missing)}; got {sorted(found)}")
        if leaked:
            failures.append(f"{case['name']}: forbidden {sorted(leaked)}")

    approved = _read_toml(root / "corpus" / "approved.toml").get("samples", [])
    annotations = _read_toml(root / "corpus" / "annotations.toml").get("annotations", [])
    approved_ids: set[str] = set()
    forbidden_fields = {"learn", "avoid_copying", "fact_note", "problem", "repair_direction", "acceptable_shapes"}
    for sample in approved:
        sample_id = sample.get("id", "<missing-id>")
        if sample_id in approved_ids:
            failures.append(f"approved corpus: duplicate id {sample_id}")
        approved_ids.add(sample_id)
        if sample.get("provenance") != "author_verbatim":
            failures.append(f"approved corpus: {sample_id} is not author_verbatim")
        leaked_fields = forbidden_fields & sample.keys()
        if leaked_fields:
            failures.append(f"approved corpus: {sample_id} contains reviewer fields {sorted(leaked_fields)}")
    annotation_ids = {item.get("id") for item in annotations}
    unknown_annotations = annotation_ids - approved_ids
    if unknown_annotations:
        failures.append(f"annotations without approved samples: {sorted(unknown_annotations)}")
    if failures:
        print(f"规则回归失败：{len(failures)} 项")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"规则回归通过：{len(cases)} 个正反样本；{len(approved)} 个作者逐字声音样本。")
    return 0


def collect_inputs(paths: list[str], recursive: bool, use_stdin: bool) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    if use_stdin:
        texts.append(("<stdin>", sys.stdin.read()))
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            files = path.rglob("*.md") if recursive else path.glob("*.md")
            texts.extend((str(file), file.read_text(encoding="utf-8")) for file in sorted(files))
        elif path.exists():
            texts.append((str(path), path.read_text(encoding="utf-8")))
        else:
            print(f"找不到：{path}", file=sys.stderr)
    return texts


def main() -> int:
    parser = argparse.ArgumentParser(description="中文技术文章文风检查器")
    parser.add_argument("paths", nargs="*", help="Markdown 文件或目录")
    parser.add_argument("-r", "--recursive", action="store_true", help="递归扫描目录中的 Markdown")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取")
    parser.add_argument("--self-test", action="store_true", help="运行规则正反样本回归")
    parser.add_argument("--list-rules", action="store_true", help="列出已加载的规则")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    args = parser.parse_args()

    if args.self_test:
        return run_self_tests()

    try:
        rules = load_rules()
    except (OSError, ValueError, tomllib.TOMLDecodeError, re.error) as error:
        print(f"规则加载失败：{error}", file=sys.stderr)
        return 1

    if args.list_rules:
        for rule in rules:
            print(f"{rule.id}\t{rule.level}\t{rule.check}\t{rule.scope}")
        return 0

    texts = collect_inputs(args.paths, args.recursive, args.stdin)
    if not texts:
        parser.error("请给出 Markdown 文件、目录、--stdin 或 --self-test")

    findings = [item for source, text in texts for item in lint_text(text, source, rules)]
    errors = sum(item.level == "error" for item in findings)
    reviews = sum(item.level == "review" for item in findings)
    if args.format == "json":
        print(json.dumps([item.as_dict() for item in findings], ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(f"[{item.level.upper():5}] {item.source}:{item.line}  ({item.rule_id}) 命中「{item.hit}」")
            print(f"        {item.message}")
        print(f"\n扫描 {len(texts)} 个文件：ERROR {errors}  REVIEW {reviews}")
        if errors:
            print("命中即阻断交付。硬禁词必须修改、不接受申辩；只有规则文字明确允许上下文裁决时，才能把争议写进问题单。")
        elif reviews:
            print("没有硬错误；REVIEW 候选必须在走查报告中引用原文并交主控二审，不能静默放行。")
        else:
            print("没有命中机械规则。仍需人工检查连贯性与事实。")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
