#!/bin/bash
# Compatible with the Bash 3.2 shipped with macOS.
set -euo pipefail
umask 077

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

INSTALL_ROOT="$HOME/Library/Application Support/kicho-bot"
FORWARDED=()
while [ "$#" -gt 0 ]; do
    case "$1" in
        --install-root|--config|--env-file|--workspace)
            [ "$#" -ge 2 ] && [ -n "$2" ] || fail "オプションにパスを指定してください: $1"
            if [ "$1" = "--install-root" ]; then
                INSTALL_ROOT="$2"
            else
                FORWARDED+=("$1" "$2")
            fi
            shift 2
            ;;
        --non-interactive) FORWARDED+=("$1"); shift ;;
        --help|-h)
            printf '%s\n' 'Usage: bash setup.command [--install-root PATH] [--config PATH] [--env-file PATH] [--workspace PATH] [--non-interactive]'
            exit 0
            ;;
        *) fail "不明なオプションです: $1" ;;
    esac
done

[ "$(uname -s)" = "Darwin" ] || fail "このセットアップはmacOS向けです。Windowsではsetup.cmdを使ってください。"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$INSTALL_ROOT"
INSTALL_ROOT="$(cd -- "$INSTALL_ROOT" && pwd)"

if command -v uv >/dev/null 2>&1; then
    UV_PATH="$(command -v uv)"
else
    UV_VERSION=0.12.5
    case "$(uname -m)" in
        arm64) TARGET=aarch64-apple-darwin ;;
        x86_64) TARGET=x86_64-apple-darwin ;;
        *) fail "Apple SiliconまたはIntelのMacを使ってください。" ;;
    esac
    UV_DIRECTORY="$INSTALL_ROOT/runtime/uv-$UV_VERSION-$TARGET"
    UV_PATH="$UV_DIRECTORY/uv"
    if [ ! -x "$UV_PATH" ]; then
        printf '%s\n' 'uvを準備しています（初回のみ）。'
        TEMPORARY="$(mktemp -d "${TMPDIR:-/tmp}/kicho-uv.XXXXXXXX")"
        trap 'rm -rf -- "$TEMPORARY"' EXIT
        ASSET="uv-$TARGET.tar.gz"
        RELEASE="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
        curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 "$RELEASE/$ASSET" -o "$TEMPORARY/$ASSET"
        curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 "$RELEASE/$ASSET.sha256" -o "$TEMPORARY/$ASSET.sha256"
        read -r EXPECTED _ < "$TEMPORARY/$ASSET.sha256"
        ACTUAL="$(shasum -a 256 "$TEMPORARY/$ASSET")"
        ACTUAL="${ACTUAL%% *}"
        [[ "$EXPECTED" =~ ^[0-9a-fA-F]{64}$ ]] && [ "$ACTUAL" = "$EXPECTED" ] || fail 'ダウンロードの検証に失敗しました。もう一度実行してください。'
        tar -xzf "$TEMPORARY/$ASSET" -C "$TEMPORARY"
        [ -f "$TEMPORARY/uv-$TARGET/uv" ] || fail 'ダウンロード内にuvが見つかりません。'
        mkdir -p "$UV_DIRECTORY"
        cp "$TEMPORARY/uv-$TARGET/uv" "$UV_PATH"
        chmod 700 "$UV_PATH"
        rm -rf -- "$TEMPORARY"
        trap - EXIT
    fi
fi

# The conditional expansion also works for empty arrays with Bash 3.2's nounset.
"$UV_PATH" run --python 3.11 --frozen --script "$SCRIPT_DIR/setup-desktop.py" \
    --uv "$UV_PATH" --install-root "$INSTALL_ROOT" ${FORWARDED[@]+"${FORWARDED[@]}"}
