"""ほかの人の Threads の投稿に、ふくいおでかけのアカウントから返信を1本出す（代表が「出して」と言ったものだけ）

2026-10-12 代表：おすすめを聞く投稿に、代表が送ったリンクへ返信案を作り、「出して」で出す（自動では探さない）。

返信先は投稿の URL（https://www.threads.com/@ユーザー名/post/コード）で渡す。
API で返信するには投稿の ID が要るので、次の順で探す:
  1. キーワード検索（KEYWORD を渡したとき）の結果から、同じ URL の投稿を探す
  2. そのユーザーの公開投稿（profile_posts）から、同じ URL の投稿を探す
  3. URL のコードを数字に直したもの（Instagram と同じ並び）を試す
同じ返信を2回出さないように、出したら state/ほかへの返信.jsonl に残す。

環境変数: THREADS_USER_ID / THREADS_ACCESS_TOKEN / POST_URL / REPLY_TEXT / KEYWORD（任意）
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from threads_bot.client import ThreadsAPIError, ThreadsClient  # noqa: E402
from threads_bot.config import Config  # noqa: E402

記録 = Path("state/ほかへの返信.jsonl")
並び = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def コードを数に(コード: str) -> str:
    n = 0
    for c in コード:
        n = n * 64 + 並び.index(c)
    return str(n)


def 同じ投稿か(permalink: str, コード: str) -> bool:
    return f"/post/{コード}" in (permalink or "")


def 探す(client: ThreadsClient, url: str, コード: str, 人: str) -> str | None:
    kw = os.environ.get("KEYWORD", "").strip()
    if kw:
        try:
            r = client._request("GET", "keyword_search", {"q": kw, "search_type": "RECENT", "fields": "id,permalink,username"})
            for p in r.get("data", []):
                if 同じ投稿か(p.get("permalink", ""), コード):
                    print(f"キーワード検索で見つけました: {p['id']}")
                    return p["id"]
            print(f"キーワード検索では見つかりません（{len(r.get('data', []))}件）")
        except ThreadsAPIError as e:
            print(f"キーワード検索が使えません: {e}")
    try:
        r = client._request("GET", "profile_posts", {"username": 人, "fields": "id,permalink", "limit": 50})
        for p in r.get("data", []):
            if 同じ投稿か(p.get("permalink", ""), コード):
                print(f"公開投稿の一覧で見つけました: {p['id']}")
                return p["id"]
        print(f"公開投稿の一覧では見つかりません（{len(r.get('data', []))}件）")
    except ThreadsAPIError as e:
        print(f"公開投稿の一覧が使えません: {e}")
    return None


def main() -> None:
    url = os.environ["POST_URL"].strip()
    text = os.environ["REPLY_TEXT"].replace("\\n", "\n").strip()
    m = re.search(r"threads\.(?:com|net)/@([^/]+)/post/([A-Za-z0-9_-]+)", url)
    if not m or not text:
        sys.exit("POST_URL（https://www.threads.com/@ユーザー名/post/コード）と REPLY_TEXT が要ります")
    人, コード = m.group(1), m.group(2)
    if 記録.exists() and any(json.loads(l).get("コード") == コード for l in 記録.read_text(encoding="utf-8").splitlines() if l.strip()):
        print("この投稿にはもう返信しています。出しません。")
        return
    cfg = Config.from_env(os.environ)
    client = ThreadsClient(cfg.user_id, cfg.access_token)
    候補 = [探す(client, url, コード, 人), コードを数に(コード)]
    for 先 in [c for c in 候補 if c]:
        try:
            c = client.create_container(text=text, reply_to_id=先)
            time.sleep(10)  # 公開の前に少し待つ（テキストでもすぐ公開すると失敗することがある）
            post_id = client.publish(c)
            link = client.permalink(post_id)
            print(f"返信しました: {link}")
            記録.parent.mkdir(parents=True, exist_ok=True)
            with 記録.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"時刻": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
                                    "返信先": url, "コード": コード, "返信": link, "post_id": post_id}, ensure_ascii=False) + "\n")
            return
        except ThreadsAPIError as e:
            print(f"返信先 {先} では出せませんでした: {e}")
    sys.exit("返信を出せませんでした（返信先の投稿の ID が分かりません）")


if __name__ == "__main__":
    main()
