#!/usr/bin/env python3
"""Register a shared skill, using unprivileged copies on Windows."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

MARKER = ".kicho-install.json"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", MARKER)


def fingerprints(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or path.suffix == ".pyc" or relative.as_posix() == MARKER:
            continue
        if path.is_symlink():
            raise ValueError(f"コピー対象内のリンクを確認してください: {path}")
        if path.is_file():
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def install_copy(skill: Path, destination: Path, files: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix=".kicho-install-", dir=destination.parent) as temp:
        staging = Path(temp)
        copied = staging / "new"
        shutil.copytree(skill, copied, ignore=IGNORE)
        if fingerprints(copied) != files:
            raise ValueError("登録中にスキルが変更されました。再実行してください。")
        (copied / MARKER).write_text(json.dumps({"version": 1, "files": files}), encoding="utf-8")
        previous = staging / "previous"
        if destination.exists():
            destination.rename(previous)
        try:
            copied.rename(destination)
        except OSError:
            if previous.exists():
                previous.rename(destination)
            raise


def install(skill: Path, base: Path, target: str, mode: str = "auto") -> list[Path]:
    skill = skill.resolve(strict=True)
    base = base.resolve(strict=True)
    if not base.is_dir() or not (skill / "SKILL.md").is_file():
        raise ValueError("登録元のSKILL.mdと登録先フォルダーを確認してください。")
    if mode == "auto":
        mode = "copy" if os.name == "nt" else "symlink"
    roots = {"codex": ".agents/skills", "claude": ".claude/skills"}
    names = roots if target == "both" else [target]
    destinations = [base / roots[name] / "kicho-bot" for name in names]
    files = fingerprints(skill) if mode == "copy" else {}
    pending = []
    for destination in destinations:
        if destination.is_symlink() and destination.resolve() == skill:
            continue
        if destination.exists() or destination.is_symlink():
            marker = destination / MARKER
            if mode != "copy" or destination.is_symlink() or not marker.is_file():
                raise ValueError(f"既存の登録を保護するため中止しました: {destination}")
            recorded = json.loads(marker.read_text(encoding="utf-8"))
            current = fingerprints(destination)
            if not isinstance(recorded, dict) or recorded.get("version") != 1 or recorded.get("files") != current:
                raise ValueError(f"登録先に変更があるため上書きしません。変更を退避してください: {destination}")
            if current == files:
                continue
        pending.append(destination)
    for destination in pending:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if mode == "copy":
            install_copy(skill, destination, files)
        else:
            destination.symlink_to(skill, target_is_directory=True)
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex / Claude Codeにkicho-botを登録します。")
    parser.add_argument("--target", choices=("both", "codex", "claude"), default="both")
    parser.add_argument("--project", type=Path, help="ユーザー全体ではなく既存プロジェクト内に登録")
    parser.add_argument("--mode", choices=("auto", "copy", "symlink"), default="auto",
                        help="auto: Windowsはコピー、Linux/macOSはシンボリックリンク")
    args = parser.parse_args()
    try:
        destinations = install(Path(__file__).resolve().parents[1] / "kicho-bot",
                               args.project or Path.home(), args.target, args.mode)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"登録できませんでした: {exc}\n")
    for destination in destinations:
        kind = "リンク" if destination.is_symlink() else "コピー"
        print(f"登録済み（{kind}）: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
