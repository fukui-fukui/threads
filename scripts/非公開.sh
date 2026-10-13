#!/usr/bin/env bash
# 外に見せない数字・記録を、非公開リポジトリ（既定 fukui-fukui/odekake-data）とやりとりする。
# 2026-10-13 代表「非公開リポジトリを作って管理して」。置くものは scripts/非公開の置き場.txt。
#
#   ./scripts/非公開.sh pull                    … 非公開の置き場から作業中のフォルダに写す（追記するファイルを消さないため、ジョブの最初に）
#   ./scripts/非公開.sh push <道筋> [メッセージ] … 作業中のフォルダから非公開の置き場に写して push する
#   ./scripts/非公開.sh is-private <道筋>        … 置き場の対象なら 0
#
# DATA_DIR で置き場のフォルダ名を決められる（既定は region.json の県。エキマエは DATA_DIR=ekimae）。
# DATA_REPO_TOKEN（odekake-data の Contents を読み書きできる鍵）が無いときは、pull は何もせず、push は 2 を返す
# （呼んだ側は今まで通り公開リポジトリにコミットする。引っ越しの前と同じ動き）。
set -euo pipefail

DATA_REPO="${DATA_REPO:-fukui-fukui/odekake-data}"
LIST="$(dirname "$0")/非公開の置き場.txt"
CLONE="${RUNNER_TEMP:-/tmp}/odekake-data"

県() {
  python3 - <<'PY'
import json
try:
    d = json.load(open("region.json", encoding="utf-8"))
except FileNotFoundError:
    d = {}
print({"石川": "ishikawa", "福井": "fukui"}.get(d.get("県名", "福井"), d.get("県名", "fukui")))
PY
}

対象一覧() { grep -v '^\s*#' "$LIST" | sed '/^\s*$/d'; }

is_private() {
  local p="${1%/}"
  while read -r x; do
    if [ "$p" = "$x" ] || [[ "$p" == "$x/"* ]]; then return 0; fi
  done < <(対象一覧)
  return 1
}

clone() {
  if [ -d "$CLONE/.git" ]; then
    git -C "$CLONE" fetch -q origin
    git -C "$CLONE" reset -q --hard "origin/$(git -C "$CLONE" rev-parse --abbrev-ref HEAD)" 2>/dev/null || true
    return
  fi
  rm -rf "$CLONE"
  git clone -q --depth 20 "${DATA_REPO_URL:-https://x-access-token:${DATA_REPO_TOKEN}@github.com/${DATA_REPO}.git}" "$CLONE"
  git -C "$CLONE" config user.name "github-actions[bot]"
  git -C "$CLONE" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
}

# .jsonl は行を合わせる（別のジョブが同時に足した行を消さないため）。ほかは上書き
写す() {
  local from="$1" to="$2"
  if [ -d "$from" ]; then
    mkdir -p "$to"
    (cd "$from" && find . -type f) | while read -r f; do 写す "$from/$f" "$to/$f"; done
    return
  fi
  mkdir -p "$(dirname "$to")"
  if [[ "$from" == *.jsonl ]] && [ -f "$to" ]; then
    python3 - "$from" "$to" <<'PY'
import sys
a, b = sys.argv[1], sys.argv[2]
seen, out = set(), []
for p in (b, a):
    for l in open(p, encoding="utf-8"):
        if l.strip() and l not in seen:
            seen.add(l)
            out.append(l if l.endswith("\n") else l + "\n")
open(b, "w", encoding="utf-8").writelines(out)
PY
  else
    cp "$from" "$to"
  fi
}

cmd="${1:-}"
case "$cmd" in
  is-private)
    is_private "${2:-}" ;;
  pull)
    if [ -z "${DATA_REPO_TOKEN:-}" ]; then echo "DATA_REPO_TOKEN が無いので、非公開の置き場は使いません。"; exit 0; fi
    clone
    k="${DATA_DIR:-$(県)}"
    while read -r x; do
      if [ -e "$CLONE/$k/$x" ]; then 写す "$CLONE/$k/$x" "$x"; fi
    done < <(対象一覧)
    echo "非公開の置き場（${DATA_REPO} の ${k}/）から写しました。" ;;
  push)
    target="${2%/}"; message="${3:-chore: 非公開の記録を更新}"
    is_private "$target" || { echo "${target} は非公開の置き場の対象ではありません。" >&2; exit 1; }
    if [ -z "${DATA_REPO_TOKEN:-}" ]; then exit 2; fi
    if [ ! -e "$target" ]; then echo "${target} がありません。"; exit 0; fi
    k="${DATA_DIR:-$(県)}"
    for attempt in 1 2 3 4; do
      clone
      写す "$target" "$CLONE/$k/$target"
      git -C "$CLONE" add -A "$k/$target"
      if git -C "$CLONE" diff --cached --quiet; then echo "${target} に変更なし。"; exit 0; fi
      git -C "$CLONE" commit -q -m "${message}（${GITHUB_REPOSITORY:-手元}）"
      if git -C "$CLONE" push -q origin HEAD; then echo "非公開の置き場に ${target} を置きました。"; exit 0; fi
      sleep $((2 ** attempt))
    done
    exit 1 ;;
  *)
    echo "使い方: $0 pull | push <道筋> [メッセージ] | is-private <道筋>" >&2; exit 1 ;;
esac
