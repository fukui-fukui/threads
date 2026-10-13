"""まちがった投稿を1本消す（手で動かす。代表の「消して」があったときだけ）

2026-10-13 代表「OK」（統括経由）の決まり：
1. 消すのは「まちがった投稿を直すとき」だけ（事実のまちがい・二重投稿・出してはいけないものが出た）。
   数字が伸びない、などの理由では消さない。
2. 消すのは代表の「消して」があったときだけ。仕組みが自動で消すことはしない。
3. 消したら、投稿の id・日時・理由だけを残し（本文は残さない）、統括に知らせる。
4. 直した投稿を出し直すときは、ふつうの予約として出す。

Threads API：DELETE /{投稿の id}（threads_basic と threads_delete の権限が要る。1アカウント1日100件まで）。

環境変数:
  THREADS_ACCESS_TOKEN … 投稿用のトークン（threads_delete 入り）
  POST_ID              … 消す投稿の id（数字）
  REASON               … 消す理由（例：日付のまちがい）
  APPROVAL             … 代表の「消して」の言葉と日時（例：10/14 9:00 統括経由「消して」）
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

API = "https://graph.threads.net/v1.0"


def call(method: str, path: str, params: dict | None = None) -> dict:
    url = f"{API}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, method=method,
                                 headers={"Authorization": f"Bearer {os.environ['THREADS_ACCESS_TOKEN']}"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.load(res)


def エラー文(e: urllib.error.HTTPError) -> str:
    try:
        err = json.load(e).get("error", {})
        return f"{e.code} code={err.get('code', '')}: {err.get('message', '')}"[:300]
    except Exception:
        return str(e.code)


def main() -> None:
    pid = os.environ.get("POST_ID", "").strip()
    理由 = os.environ.get("REASON", "").strip()
    指示 = os.environ.get("APPROVAL", "").strip()
    if not pid.isdigit():
        sys.exit("POST_ID は消す投稿の id（数字）を入れてください")
    if not 理由 or not 指示:
        sys.exit("理由と、代表の「消して」（いつ・どこで）の両方を入れてください。代表の指示が無い投稿は消しません")
    try:
        自分 = call("GET", "me", {"fields": "username"}).get("username")
        投稿 = call("GET", pid, {"fields": "id,username,timestamp"})
    except urllib.error.HTTPError as e:
        sys.exit(f"::error::投稿を確かめられません（{エラー文(e)}）")
    if 投稿.get("username") != 自分:
        sys.exit("::error::このアカウントの投稿ではないので消しません")
    try:
        r = call("DELETE", pid)
    except urllib.error.HTTPError as e:
        print(f"::error::消せませんでした（{エラー文(e)}）")
        if e.code in (400, 403):
            print("権限の候補：threads_delete。鍵を作り直して、この権限を入れる必要があります。")
        sys.exit(1)
    if not r.get("success", True):
        sys.exit(f"::error::消せませんでした（{r}）")
    今 = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")
    # 本文は残さない（id・日時・理由・代表の指示だけ）
    print(json.dumps({"消した投稿": pid, "投稿の日時": 投稿.get("timestamp"), "消した日時": 今,
                      "理由": 理由, "代表の指示": 指示}, ensure_ascii=False))


if __name__ == "__main__":
    main()
