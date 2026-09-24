"""UTF-8 CLI output independent of shell redirection and system locale."""
import json
import os
from pathlib import Path
import sys
import tempfile


def configure_stdio() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def write_json(value: object, path: Path | None) -> int:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(text, end="")
        return 0
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".kicho-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write(text)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except OSError:
        print("判定JSONを保存できません。出力先フォルダーと書込権限を確認してください。", file=sys.stderr)
        return 2
    return 0
