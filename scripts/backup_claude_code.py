#!/usr/bin/env python3
"""Backup Claude Code state for a WSL migration.

Collects small Claude Code state files plus project-level Claude guidance from
direct children of the home directory. It intentionally does not copy full
projects, and by default it also avoids large Claude cache/history payloads:
source code should be restored from git, while this package preserves the JSON,
and Markdown files that help Claude Code rebuild its context.

Usage:
  python3 scripts/backup_claude_code.py
  python3 scripts/backup_claude_code.py --dry-run
  python3 scripts/backup_claude_code.py --keep-staging
  python3 scripts/backup_claude_code.py --full
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "backups" / "claude-code"

GLOBAL_CLAUDE_CANDIDATES = [
    ".claude",
    ".claude.json",
    ".claude.json.backup",
    ".config/claude",
    ".local/share/claude",
]

PROJECT_STATE_NAMES = [".claude", "CLAUDE.md"]
LEAN_SUFFIXES = {".json", ".md"}
OPTIONAL_JSONL_SUFFIX = ".jsonl"
DEFAULT_MAX_FILE_MB = 1
LEAN_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "books",
    "build",
    "cache",
    "caches",
    "chapters",
    "debug",
    "dist",
    "file-history",
    "ide",
    "images",
    "node_modules",
    "projects",
    "session-env",
    "shell-snapshots",
    "venv",
    "worktrees",
}


@dataclass
class CopyItem:
    source: Path
    target: Path
    label: str


def rel_to_home(path: Path, home: Path) -> Path:
    return path.resolve(strict=False).relative_to(home.resolve(strict=False))


def run_text(cmd: list[str], cwd: Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip() or None


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ["B", "K", "M", "G", "T"]:
        if value < 1024 or unit == "T":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{num_bytes}B"


def path_size(path: Path) -> int:
    if path.is_symlink():
        return len(os.readlink(path))
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        root_path = Path(root)
        for name in dirs:
            child = root_path / name
            if child.is_symlink():
                total += len(os.readlink(child))
        for name in files:
            child = root_path / name
            try:
                total += child.stat().st_size if not child.is_symlink() else len(os.readlink(child))
            except OSError:
                pass
    return total


def count_tree(path: Path) -> tuple[int, int]:
    if path.is_file() or path.is_symlink():
        return 1, 0
    files = 0
    dirs = 0
    for _, dirnames, filenames in os.walk(path, followlinks=False):
        dirs += len(dirnames)
        files += len(filenames)
    return files, dirs


def copy_path(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir() and not src.is_symlink():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=True)
    else:
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        shutil.copy2(src, dst, follow_symlinks=False)


def should_include_lean_file(path: Path, max_file_bytes: int, suffixes: set[str]) -> bool:
    if path.name == ".claude.json.backup":
        return True
    if path.suffix.lower() not in suffixes:
        return False
    try:
        return path_size(path) <= max_file_bytes
    except OSError:
        return False


def discover_lean_files(
    src: Path,
    dst_root: Path,
    label_root: str,
    max_file_bytes: int,
    suffixes: set[str],
) -> list[CopyItem]:
    if src.is_file() or src.is_symlink():
        if should_include_lean_file(src, max_file_bytes, suffixes):
            return [CopyItem(src, dst_root, label_root)]
        return []

    items: list[CopyItem] = []
    for root, dirs, files in os.walk(src, followlinks=False):
        dirs[:] = [
            name
            for name in dirs
            if name not in LEAN_EXCLUDE_DIRS and not (Path(root) / name).is_symlink()
        ]
        root_path = Path(root)
        for name in files:
            child = root_path / name
            if should_include_lean_file(child, max_file_bytes, suffixes):
                rel = child.relative_to(src)
                items.append(CopyItem(child, dst_root / rel, f"{label_root}/{rel}"))
    return items


def discover_global_items(
    home: Path,
    payload: Path,
    full: bool,
    max_file_bytes: int,
    suffixes: set[str],
) -> list[CopyItem]:
    items: list[CopyItem] = []
    for rel in GLOBAL_CLAUDE_CANDIDATES:
        src = home / rel
        if src.exists() or src.is_symlink():
            target = payload / "home" / rel
            if full:
                items.append(CopyItem(src, target, f"global:{rel}"))
            else:
                items.extend(discover_lean_files(src, target, f"global:{rel}", max_file_bytes, suffixes))
    return items


def git_info(project: Path) -> dict[str, Any]:
    if not (project / ".git").exists():
        return {"is_git": False}
    remotes = run_text(["git", "remote", "-v"], cwd=project) or ""
    remote_map: dict[str, dict[str, str]] = {}
    for line in remotes.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            name, url, kind = parts[0], parts[1], parts[2].strip("()")
            remote_map.setdefault(name, {})[kind] = url
    return {
        "is_git": True,
        "branch": run_text(["git", "branch", "--show-current"], cwd=project),
        "head": run_text(["git", "rev-parse", "--short", "HEAD"], cwd=project),
        "dirty": bool(run_text(["git", "status", "--porcelain"], cwd=project)),
        "remotes": remote_map,
    }


def discover_projects(home: Path) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for child in sorted(home.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name.startswith("."):
            continue
        state_paths = [name for name in PROJECT_STATE_NAMES if (child / name).exists() or (child / name).is_symlink()]
        info: dict[str, Any] = {
            "name": child.name,
            "path": str(child),
            "state_paths": state_paths,
            "has_claude_state": bool(state_paths),
        }
        info.update(git_info(child))
        projects.append(info)
    return projects


def discover_project_items(
    home: Path,
    payload: Path,
    projects: list[dict[str, Any]],
    full: bool,
    max_file_bytes: int,
    suffixes: set[str],
) -> list[CopyItem]:
    items: list[CopyItem] = []
    for project in projects:
        project_path = Path(project["path"])
        for name in project["state_paths"]:
            src = project_path / name
            target = payload / "projects" / project_path.name / name
            if full:
                items.append(CopyItem(src, target, f"project:{project_path.name}/{name}"))
            else:
                items.extend(
                    discover_lean_files(
                        src,
                        target,
                        f"project:{project_path.name}/{name}",
                        max_file_bytes,
                        suffixes,
                    )
                )
    return items


def collect_environment(home: Path) -> dict[str, Any]:
    claude_path = shutil.which("claude")
    return {
        "host": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "home": str(home),
        "shell": os.environ.get("SHELL"),
        "claude_bin": claude_path,
        "claude_version": run_text(["claude", "--version"]) if claude_path else None,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_restore_guide(staging: Path, manifest: dict[str, Any], projects: list[dict[str, Any]]) -> None:
    archive_name = manifest["archive_name"]
    guide = f"""# Claude Code WSL Restore Guide

Backup created: {manifest["created_at"]}
Source home: `{manifest["source_home"]}`

This backup contains Claude Code small state files and project-level Claude
guidance from direct children of the source home directory. It does not contain
full project source trees. In the default lean mode it includes only small JSON
and Markdown files under the Claude state roots. JSONL conversation logs are
included only when the backup was created with `--include-jsonl`.
Runtime logs/caches are skipped in lean mode.

## What is inside

- `payload/home/.claude/`: small global Claude Code state files such as settings, memory, plans, and JSON metadata.
- `payload/home/.claude.json`: top-level Claude Code config/state when present.
- `payload/projects/<project>/`: project-level `CLAUDE.md` and small `.claude/` JSON/Markdown state from one-level projects under the old home.
- `project_inventory.json`: git remotes, branches, dirty flags, and Claude state presence.
- `restore_claude_code.sh`: helper script for restoring files into a new WSL home.

## Suggested restore order

1. Install Claude Code on the new WSL and run it once so the base directories exist.
2. Clone this WorkChop repository.
3. Put `{archive_name}` in `backups/claude-code/`, then extract it:

   ```bash
   mkdir -p /tmp/cc-restore
   tar -xzf backups/claude-code/{archive_name} -C /tmp/cc-restore
   cd /tmp/cc-restore/{manifest["backup_name"]}
   ```

4. Recreate project directories from `project_inventory.json`. Keeping the same paths under `$HOME` gives Claude Code the best chance to reconnect old project state.
5. Run the helper:

   ```bash
   ./restore_claude_code.sh
   ```

6. Start Claude Code inside the restored projects. If a project moved paths, open it once and let Claude rebuild path-specific project entries.

## Project clone hints

Projects with git remotes are listed below. Dirty projects had uncommitted local changes at backup time, so check those old worktrees before wiping the old machine.

"""
    for project in projects:
        if not project.get("is_git"):
            continue
        fetch = None
        origin = project.get("remotes", {}).get("origin", {})
        if isinstance(origin, dict):
            fetch = origin.get("fetch") or origin.get("push")
        dirty = " dirty" if project.get("dirty") else ""
        branch = project.get("branch") or "unknown-branch"
        guide += f"- `{project['name']}`: `{fetch or 'no origin remote'}` ({branch}{dirty})\n"
    (staging / "restore_guide.md").write_text(guide, encoding="utf-8")


def write_restore_script(staging: Path) -> None:
    script = """#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="$SRC_DIR/payload"
TARGET_HOME="${TARGET_HOME:-$HOME}"
PROJECT_ROOT="${PROJECT_ROOT:-$TARGET_HOME}"
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "Restoring Claude Code state into: $TARGET_HOME"
echo "Project root: $PROJECT_ROOT"

backup_existing() {
  local path="$1"
  if [ -e "$path" ] || [ -L "$path" ]; then
    local backup="$path.before-cc-restore-$STAMP"
    echo "  existing -> $backup"
    mv "$path" "$backup"
  fi
}

if [ -d "$PAYLOAD/home" ]; then
  while IFS= read -r -d '' item; do
    rel="${item#"$PAYLOAD/home/"}"
    dest="$TARGET_HOME/$rel"
    mkdir -p "$(dirname "$dest")"
    backup_existing "$dest"
    cp -a "$item" "$dest"
    echo "  restored $dest"
  done < <(find "$PAYLOAD/home" -mindepth 1 -maxdepth 1 -print0)
fi

if [ -d "$PAYLOAD/projects" ]; then
  while IFS= read -r -d '' project_dir; do
    project_name="$(basename "$project_dir")"
    dest_project="$PROJECT_ROOT/$project_name"
    if [ ! -d "$dest_project" ]; then
      echo "  skip project state for $project_name (missing $dest_project)"
      continue
    fi
    while IFS= read -r -d '' state_item; do
      rel="${state_item#"$project_dir/"}"
      dest="$dest_project/$rel"
      mkdir -p "$(dirname "$dest")"
      backup_existing "$dest"
      cp -a "$state_item" "$dest"
      echo "  restored $dest"
    done < <(find "$project_dir" -mindepth 1 -maxdepth 1 -print0)
  done < <(find "$PAYLOAD/projects" -mindepth 1 -maxdepth 1 -type d -print0)
fi

echo "Done. Open Claude Code in your restored projects to let it refresh path-specific state."
"""
    path = staging / "restore_claude_code.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def make_archive(staging: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(staging, arcname=staging.name, recursive=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backup Claude Code state for WSL migration.")
    parser.add_argument("--home", type=Path, default=Path.home(), help="home directory to scan")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="backup output directory")
    parser.add_argument("--name", help="backup directory/archive basename")
    parser.add_argument("--dry-run", action="store_true", help="show what would be collected")
    parser.add_argument("--no-archive", action="store_true", help="leave only the staging directory")
    parser.add_argument("--keep-staging", action="store_true", help="keep staging directory after archive")
    parser.add_argument("--full", action="store_true", help="copy whole Claude state directories instead of only small json/md files")
    parser.add_argument("--include-jsonl", action="store_true", help="include jsonl logs in lean mode")
    parser.add_argument(
        "--max-file-mb",
        type=int,
        default=DEFAULT_MAX_FILE_MB,
        help="max file size for lean mode; ignored with --full",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    home = args.home.expanduser().resolve()
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = args.name or f"claude-code-state-{stamp}"
    out_dir = args.output.expanduser().resolve()
    staging = out_dir / backup_name
    payload = staging / "payload"
    lean_suffixes = set(LEAN_SUFFIXES)
    if args.include_jsonl:
        lean_suffixes.add(OPTIONAL_JSONL_SUFFIX)

    max_file_bytes = args.max_file_mb * 1024 * 1024
    global_items = discover_global_items(home, payload, args.full, max_file_bytes, lean_suffixes)
    projects = discover_projects(home)
    project_items = discover_project_items(home, payload, projects, args.full, max_file_bytes, lean_suffixes)
    all_items = global_items + project_items

    item_summaries = []
    total_bytes = 0
    for item in all_items:
        try:
            size = path_size(item.source)
            files, dirs = count_tree(item.source)
        except OSError:
            size, files, dirs = 0, 0, 0
        total_bytes += size
        item_summaries.append(
            {
                "label": item.label,
                "source": str(item.source),
                "target": str(item.target.relative_to(staging)),
                "bytes": size,
                "files": files,
                "dirs": dirs,
            }
        )

    print("Claude Code backup plan")
    print(f"  home: {home}")
    print(f"  output: {out_dir}")
    print(f"  items: {len(all_items)}")
    suffix_label = "/".join(sorted(s.lstrip(".") for s in lean_suffixes))
    print(f"  mode: {'full' if args.full else f'lean {suffix_label} <= {args.max_file_mb}MB'}")
    print(f"  estimated payload: {human_size(total_bytes)}")
    print(f"  projects scanned: {len(projects)} (one level only)")
    print(f"  projects with Claude state: {sum(1 for p in projects if p['has_claude_state'])}")

    if args.dry_run:
        print("\nDry run only. Top items:")
        for item in sorted(item_summaries, key=lambda x: x["bytes"], reverse=True)[:12]:
            print(f"  {human_size(item['bytes']).rjust(8)}  {item['label']}  <- {item['source']}")
        return

    if staging.exists():
        raise SystemExit(f"Backup directory already exists: {staging}")
    out_dir.mkdir(parents=True, exist_ok=True)
    payload.mkdir(parents=True, exist_ok=True)

    for item in all_items:
        copy_path(item.source, item.target)

    archive_name = f"{backup_name}.tar.gz"
    manifest: dict[str, Any] = {
        "backup_name": backup_name,
        "archive_name": archive_name,
        "created_at": created_at,
        "source_home": str(home),
        "project_scan_depth": 1,
        "mode": "full" if args.full else "lean",
        "lean_suffixes": sorted(lean_suffixes),
        "lean_max_file_mb": None if args.full else args.max_file_mb,
        "lean_exclude_dirs": [] if args.full else sorted(LEAN_EXCLUDE_DIRS),
        "global_candidates": GLOBAL_CLAUDE_CANDIDATES,
        "project_state_names": PROJECT_STATE_NAMES,
        "environment": collect_environment(home),
        "payload_bytes": total_bytes,
        "payload_human_size": human_size(total_bytes),
        "items": item_summaries,
    }

    write_json(staging / "manifest.json", manifest)
    write_json(staging / "project_inventory.json", projects)
    write_restore_guide(staging, manifest, projects)
    write_restore_script(staging)

    archive_path = out_dir / archive_name
    if not args.no_archive:
        make_archive(staging, archive_path)
        manifest["archive_bytes"] = archive_path.stat().st_size
        manifest["archive_human_size"] = human_size(archive_path.stat().st_size)
        write_json(staging / "manifest.json", manifest)
        guide_copy = out_dir / f"{backup_name}-restore_guide.md"
        shutil.copy2(staging / "restore_guide.md", guide_copy)
        if not args.keep_staging:
            shutil.rmtree(staging)
        print(f"\nCreated archive: {archive_path}")
        print(f"Restore guide:    {guide_copy}")
    else:
        print(f"\nCreated staging directory: {staging}")

    print("Note: this package may contain auth/session material. Store it like a secret.")


if __name__ == "__main__":
    main()
