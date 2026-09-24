#!/usr/bin/env python3
"""Register the shared skill without replacing existing files or links."""

import argparse
from pathlib import Path


def install(skill: Path, base: Path, target: str) -> list[Path]:
    skill = skill.resolve(strict=True)
    base = base.resolve(strict=True)
    if not base.is_dir() or not (skill / "SKILL.md").is_file():
        raise ValueError("登録元のSKILL.mdと登録先フォルダーを確認してください。")
    roots = {"codex": ".agents/skills", "claude": ".claude/skills"}
    names = roots if target == "both" else [target]
    destinations = [base / roots[name] / "kicho-bot" for name in names]
    for destination in destinations:
        if destination.is_symlink() and destination.resolve() == skill:
            continue
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"既存の登録を保護するため中止しました: {destination}")
    for destination in destinations:
        if not destination.is_symlink():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.symlink_to(skill, target_is_directory=True)
    return destinations


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex / Claude Codeにkicho-botを登録します。")
    parser.add_argument("--target", choices=("both", "codex", "claude"), default="both")
    parser.add_argument("--project", type=Path, help="ユーザー全体ではなく既存プロジェクト内に登録")
    args = parser.parse_args()
    try:
        destinations = install(Path(__file__).resolve().parents[1] / "kicho-bot",
                               args.project or Path.home(), args.target)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"登録できませんでした: {exc}\n")
    for destination in destinations:
        print(f"登録済み: {destination} -> {destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
