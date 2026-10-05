#!/usr/bin/env python3
"""Bake build/<lane>/<role>.md from combos/*.json - the two-axis compiler.

content-forge 的编辑链有六个读者(主控、写手、四道走查),所以烘焙按
「赛道 x 角色」两轴出包:combos/<lane>.json 选层,本文件的 ROLE_MATRIX
决定每种角色包装哪些层、带不带语料。层卡全文内联;语料(VOICE/COMPARE/
approved)用 <!-- corpus:... --> 标记裹住原文烘进包,一字不动、不摘要。
剥除逻辑(lint 块、## 来源)只作用于层卡,永远不碰语料——这是与上游
speak-understandable 版本的关键分叉。

互斥靠数据结构:base/voice 是单值键,同维装两份在清单层面就写不进去;
「写手禁审稿层、四道走查互相隔离、保真不读语料」住 ROLE_MATRIX,
改那张表等于改红线。

--check 对账:resolve 硬错或产物与正本漂移,exit 1。尚未烘焙只提示,
exit 0,干净 clone 上 doctor 不许全红。

自包含扫描:渲染后扫描包文本。/home/ 视为路径泄漏,烘焙直接失败。
../ 、.claude/ 、content-forge 在正文里多为合法提及(环境变量名、站内
说明),只计数列出供人工过目,不阻断。

用法:
  python3 tools/bake.py [lane]      # 烘一个赛道,缺省全部
  python3 tools/bake.py --check     # 只校验不写文件

build/ 是生成物:别手改,改 recipes/ 与 combos/ 再重跑。
"""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMBOS_DIR = REPO / "combos"
BUILD_DIR = REPO / "build"

CORPUS_DIR_NAME = "tools/humanizer-zh/corpus"
CORPUS_FILES = ("VOICE.md", "COMPARE.md", "approved.toml")

LAYER_DIMS = ("base", "process", "review", "voice", "scene")
DIM_LABEL = {"base": "基座", "process": "流程", "review": "审稿",
             "voice": "声音", "scene": "场景"}
ROLE_NAMES = ("master", "writer", "voice-walker", "fidelity-walker",
              "thread-walker", "reference-walker")
COMBO_KEYS = {"lane", "base", "process", "review", "voice", "scene",
              "roles", "role_layer_extras"}

PRIORITY_LINE = ("冲突时:作者最新裁决 > base/forge-base 宪法 > process 流程与验收"
                 " > review/voice 判据 > scene 场景 > 角色卡操作指令。")

LINT_BLOCK = re.compile(r"```lint\n.*?\n```", re.S)
LINT_PLACEHOLDER = "(机械判罚块,略)"
SOURCE_SECTION = re.compile(r"\n## 来源\n.*?(?=\n## |\Z)", re.S)

# 每种角色包装哪些层、带不带语料。语料跟随 voice 层:清单没选声音卡,
# 任何角色都不带语料。场景层各角色都带(共享语境)。
ROLE_MATRIX = {
    "master": {"layers": ["base", "process", "review", "voice", "scene"], "corpus": False},
    "writer": {"layers": ["base", "voice", "scene"], "corpus": True},
    "voice-walker": {"layers": ["voice", "scene"], "corpus": True},
    "fidelity-walker": {"layers": ["base", "scene"], "corpus": False},
    "thread-walker": {"layers": ["base", "scene"], "corpus": False},
    "reference-walker": {"layers": ["base", "scene"], "corpus": False},
}

FATAL_PATH = re.compile(r"/home/")
WARN_PATHS = (re.compile(r"\.\./"), re.compile(r"\.claude/"), re.compile(r"content-forge"))


def strip_meta(text):
    """层卡专用:剥掉给脚本的 lint 块和给维护者的来源节。语料永远不走这里。"""
    text = LINT_BLOCK.sub(LINT_PLACEHOLDER, text)
    return SOURCE_SECTION.sub("", text)


def layer_desc(path):
    """取层卡标题里的一句话描述:全角冒号之后、半角括号之前。"""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                title = line[1:].strip()
                if "：" in title:
                    title = title.split("：", 1)[1]
                if "(" in title:
                    title = title.split("(", 1)[0]
                return title.strip()
    except OSError:
        pass
    return path.stem


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_text(path):
    return path.read_text(encoding="utf-8")


def resolve(combo, repo=None):
    """清单 -> 有序层列表。错误聚合后一次 raise,文案学上游:指名道姓加可选值。"""
    repo = Path(repo) if repo else REPO
    errors = []
    layers = []

    def card(dim, name):
        dirname = "scenes" if dim == "scene" else dim
        p = repo / "recipes" / dirname / (name + ".md")
        if not p.is_file():
            errors.append(f"{dim} 层 {name} 不存在:{p}")
            return None
        return p

    unknown = sorted(set(combo) - COMBO_KEYS)
    if unknown:
        errors.append(f"未知清单字段:{','.join(unknown)}(可用:{','.join(sorted(COMBO_KEYS))})")
    if not isinstance(combo.get("lane"), str) or not combo.get("lane"):
        errors.append("lane 必须是非空字符串")

    for dim in ("base", "voice", "scene"):
        val = combo.get(dim)
        if val is None:
            if dim == "base":
                errors.append("base 必装,清单里缺 base")
            continue
        if not isinstance(val, str):
            errors.append(f"{dim} 是单值键(一次一份),收到列表或对象")
            continue
        p = card(dim, val)
        if p:
            layers.append((dim, val, layer_desc(p), p))
    for dim in ("process", "review"):
        val = combo.get(dim)
        if val is None:
            continue
        if not isinstance(val, list):
            errors.append(f"{dim} 应是列表")
            continue
        for name in val:
            p = card(dim, name)
            if p:
                layers.append((dim, name, layer_desc(p), p))

    roles = combo.get("roles")
    if not isinstance(roles, list) or not roles:
        errors.append("roles 应是非空列表")
        roles = []
    for r in roles:
        if r not in ROLE_NAMES:
            errors.append(f"未知角色:{r}(可用:{','.join(ROLE_NAMES)})")
        elif not (repo / "recipes" / "roles" / (r + ".md")).is_file():
            errors.append(f"角色卡 {r} 不存在:{repo / 'recipes' / 'roles' / (r + '.md')}")

    extras = combo.get("role_layer_extras")
    if extras is not None:
        if not isinstance(extras, dict):
            errors.append("role_layer_extras 应是对象(角色名 -> 维度列表)")
        else:
            for r, dims in extras.items():
                if r not in ROLE_NAMES:
                    errors.append(f"role_layer_extras 引用未知角色:{r}")
                bad = [d for d in dims if d not in LAYER_DIMS]
                if bad:
                    errors.append(f"role_layer_extras[{r}] 引用未知维度:{','.join(bad)}")

    if errors:
        raise ValueError("\n".join(errors))
    ordered = [l for d in LAYER_DIMS for l in layers if l[0] == d]
    return ordered, roles


def role_card(repo, role):
    return Path(repo) / "recipes" / "roles" / (role + ".md")


def role_sections(combo, layers, role, repo):
    """一种角色 -> (该读的层 + 自己的角色卡, 是否带语料)。"""
    spec = ROLE_MATRIX[role]
    dims = list(spec["layers"]) + [d for d in (combo.get("role_layer_extras") or {}).get(role, [])]
    secs = [l for l in layers if l[0] in dims]
    rc = role_card(repo, role)
    secs.append(("roles", role, layer_desc(rc), rc))
    return secs, spec["corpus"] and bool(combo.get("voice"))


def combo_digest(combo, layers, roles, repo):
    """清单 + 全部所选层卡 + 角色卡 + 语料的联合指纹,截 12 位。"""
    repo = Path(repo)
    payload = {"combo": combo,
               "layers": {str(p.relative_to(repo)): sha256_file(p) for _, _, _, p in layers},
               "roles": {r: sha256_file(role_card(repo, r)) for r in roles},
               "corpus": {n: sha256_file(repo / CORPUS_DIR_NAME / n) for n in CORPUS_FILES}}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


def build_route(combo, layers, roles):
    parts = []
    for d in LAYER_DIMS:
        names = [l[1] for l in layers if l[0] == d]
        if names:
            parts.append(f"{DIM_LABEL[d]}:{'、'.join(names)}")
    parts.append(f"角色:{'、'.join(roles)}")
    return ",".join(parts)


def render_pack(lane, role, secs, with_corpus, digest, route, repo):
    repo = Path(repo)
    lines = [f"# {lane}/{role} 组合包(由 tools/bake.py 生成;改 combos/{lane}.json 与 recipes/ 再重跑,别手改本文件)", ""]
    lines.append(f"路由:{route}。")
    lines.append(PRIORITY_LINE)
    lines.append(f"combo:{digest}")
    if with_corpus:
        prints = "、".join(f"{n} {sha256_file(repo / CORPUS_DIR_NAME / n)[:8]}" for n in CORPUS_FILES)
        lines.append(f"语料指纹:{prints}")
    else:
        lines.append("语料:本角色不读语料")
    lines.append("说明:本包自包含,可直接拷贝分发。收尾的机器体检脚本住在仓库里(humanizer_lint、review_gate),包离开仓库时降级为模型走查加人工验收,并在报告中注明降级。")
    lines.append("")
    for dim, name, desc, path in secs:
        lines.append(f"----- {desc}({path.name})-----")
        lines.append(strip_meta(read_text(path)))
        lines.append("")
    if with_corpus:
        for n in CORPUS_FILES:
            lines.append(f"----- 语料:{n}(全文,未删改)-----")
            lines.append(f"<!-- corpus:{n} -->")
            lines.append(read_text(repo / CORPUS_DIR_NAME / n).rstrip("\n"))
            lines.append("<!-- /corpus -->")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def scan_pack(text, lane, role):
    """自包含扫描:/home/ 致命,其余计数供人工过目。"""
    fatal = [ln for ln in text.splitlines() if FATAL_PATH.search(ln)]
    if fatal:
        raise ValueError(f"{lane}/{role} 包内出现绝对用户路径(疑似泄漏),前几行:" + " | ".join(fatal[:3]))
    warns = {}
    for pat in WARN_PATHS:
        n = sum(1 for ln in text.splitlines() if pat.search(ln))
        if n:
            warns[pat.pattern] = n
    return warns


def bake_combo(repo, combo_path):
    repo = Path(repo)
    combo = json.loads(read_text(combo_path))
    layers, roles = resolve(combo, repo=repo)
    lane = combo["lane"]
    digest = combo_digest(combo, layers, roles, repo)
    route = build_route(combo, layers, roles)
    out_dir = repo / "build" / lane
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {"lane": lane, "packs": [], "warnings": []}
    for role in roles:
        secs, with_corpus = role_sections(combo, layers, role, repo)
        text = render_pack(lane, role, secs, with_corpus, digest, route, repo)
        warns = scan_pack(text, lane, role)
        (out_dir / (role + ".md")).write_text(text, encoding="utf-8")
        summary["packs"].append(role + ".md")
        if warns:
            summary["warnings"].append({role: warns})
    lock_files = {str(p.relative_to(repo)): sha256_file(p) for _, _, _, p in layers}
    for r in roles:
        rp = role_card(repo, r)
        lock_files[str(rp.relative_to(repo))] = sha256_file(rp)
    for n in CORPUS_FILES:
        cp = repo / CORPUS_DIR_NAME / n
        lock_files[str(cp.relative_to(repo))] = sha256_file(cp)
    lock = {"combo_hash": digest, "files": lock_files}
    (out_dir / ".bake-lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def check_combo(repo, combo_path):
    """三态:ok / missing(未烘焙,不算错) / drift(漂移) / error(清单或层卡坏)。"""
    repo = Path(repo)
    try:
        combo = json.loads(read_text(combo_path))
        layers, roles = resolve(combo, repo=repo)
    except (ValueError, json.JSONDecodeError, OSError) as err:
        return "error", [f"{combo_path.name}: {err}"]
    lane = combo["lane"]
    out_dir = repo / "build" / lane
    if not out_dir.is_dir():
        return "missing", []
    digest = combo_digest(combo, layers, roles, repo)
    route = build_route(combo, layers, roles)
    drift = []
    for role in roles:
        secs, with_corpus = role_sections(combo, layers, role, repo)
        text = render_pack(lane, role, secs, with_corpus, digest, route, repo)
        disk = out_dir / (role + ".md")
        if not disk.is_file() or read_text(disk) != text:
            drift.append(role + ".md")
    try:
        lock = json.loads(read_text(out_dir / ".bake-lock.json"))
    except (OSError, json.JSONDecodeError):
        lock = {}
    if lock.get("combo_hash") != digest:
        drift.append(".bake-lock.json")
    if drift:
        return "drift", sorted(set(drift))
    return "ok", []


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    wanted = [a for a in args if not a.startswith("--")]
    combos = sorted(COMBOS_DIR.glob("*.json"))
    if not combos:
        print("combos/ 下没有选层清单。", file=sys.stderr)
        return 2
    if wanted:
        names = {c.stem for c in combos}
        unknown = [w for w in wanted if w not in names]
        if unknown:
            print(f"未知赛道:{','.join(unknown)}(可用:{','.join(sorted(names))})", file=sys.stderr)
            return 2
        combos = [c for c in combos if c.stem in set(wanted)]
    if check_only:
        bad = 0
        for c in combos:
            status, notes = check_combo(REPO, c)
            if status == "ok":
                print(f"  ✓ {c.stem} 产物与正本一致")
            elif status == "missing":
                print(f" · {c.stem} 尚未烘焙(跑 workchop bake 生成,INFO)")
            else:
                bad = 1
                print(f"  ✗ {c.stem} {status}: {', '.join(notes) if notes else ''}")
        return 1 if bad else 0
    for c in combos:
        try:
            s = bake_combo(REPO, c)
        except (ValueError, OSError) as err:
            print(f"烘焙失败 {c.name}:\n{err}", file=sys.stderr)
            return 2
        print(f"已烘 {s['lane']}: {'、'.join(s['packs'])}")
        for w in s["warnings"]:
            print(f"  提示 {s['lane']} 自包含扫描(人工过目): {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
