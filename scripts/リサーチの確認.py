"""バズ投稿リサーチを自動でできるかの確認（2026-11-01 代表「はい。おでかけ　福井　で調べて」）

Threads API で、ほかの人の投稿の「いいね数」などの数字が取れるかを確かめる。
読むだけで、投稿・返信はしない。結果はログに出し、state には残さない。

試すこと:
  1. keyword_search（TOP / RECENT）に like_count などの数字の項目を付けて頼む
  2. 見つかった投稿1本を ID で読み、数字の項目を頼む
  3. その投稿の insights（likes など）を頼む（自分の投稿でないと断られるはず）
  4. その投稿者の profile_posts に数字の項目を付けて頼む
  5. その投稿の replies（ツリーの続きが取れるか）

環境変数: THREADS_USER_ID / THREADS_ACCESS_TOKEN / KEYWORD（既定「おでかけ 福井」）
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from threads_bot.client import ThreadsAPIError, ThreadsClient  # noqa: E402
from threads_bot.config import Config  # noqa: E402

基本 = "id,username,text,permalink,timestamp,media_type"
数字 = ["like_count", "likes", "reply_count", "replies_count", "repost_count", "quote_count", "views"]


def 頼む(client: ThreadsClient, 名前: str, path: str, params: dict) -> dict | None:
    try:
        r = client._request("GET", path, params)
    except ThreadsAPIError as e:
        print(f"  × {名前}: {e}")
        return None
    print(f"  ○ {名前}: 返ってきた")
    return r


def 項目を探る(client: ThreadsClient, 名前: str, path: str, params: dict) -> dict | None:
    """数字の項目を全部付けて頼み、断られたら1つずつ試して、通る項目を調べる"""
    r = 頼む(client, f"{名前}（数字の項目を全部付ける）", path, {**params, "fields": 基本 + "," + ",".join(数字)})
    if r is not None:
        return r
    通る = []
    for f in 数字:
        if 頼む(client, f"{名前}（{f} だけ足す）", path, {**params, "fields": 基本 + "," + f}) is not None:
            通る.append(f)
    print(f"  → 通った数字の項目: {通る or 'なし'}")
    return 頼む(client, f"{名前}（基本の項目＋通った項目）", path, {**params, "fields": ",".join([基本, *通る])})


def 見せる(r: dict | None, 件数: int = 5) -> list[dict]:
    data = (r or {}).get("data", [])
    if isinstance(r, dict) and "data" not in r and r.get("id"):
        data = [r]
    print(f"  件数: {len(data)}")
    for p in data[:件数]:
        数 = {k: p[k] for k in 数字 if k in p}
        本文 = (p.get("text") or "").replace("\n", " ")[:60]
        print(f"   - @{p.get('username')} {p.get('timestamp', '')[:10]} 数字={数 or 'なし'} {p.get('permalink')}")
        print(f"     {本文}")
    if data:
        print(f"  1件目の項目名: {sorted(data[0].keys())}")
    return data


def main() -> None:
    kw = os.environ.get("KEYWORD", "").strip() or "おでかけ 福井"
    cfg = Config.from_env(os.environ)
    client = ThreadsClient(cfg.user_id, cfg.access_token, max_retries=2)
    print(f"キーワード: {kw}\n")

    見つけた: list[dict] = []
    for 種類 in ["TOP", "RECENT"]:
        print(f"■ 1. keyword_search {種類}")
        r = 項目を探る(client, "検索", "keyword_search", {"q": kw, "search_type": 種類, "limit": 25})
        見つけた += 見せる(r)
        print()

    if not 見つけた:
        print("投稿が見つからないので、2〜5 は試せません。")
        return
    p = 見つけた[0]
    print(f"■ 2. 投稿を ID で読む（{p.get('permalink')}）")
    見せる(項目を探る(client, "投稿", p["id"], {}))
    print()

    print("■ 3. insights")
    r = 頼む(client, "insights", f"{p['id']}/insights", {"metric": "likes,replies,reposts,quotes,views"})
    if r is not None:
        print("  " + json.dumps(r, ensure_ascii=False)[:600])
    print()

    if p.get("username"):
        print(f"■ 4. profile_posts（@{p['username']}）")
        見せる(項目を探る(client, "公開投稿", "profile_posts", {"username": p["username"], "limit": 10}), 3)
        print()

    print("■ 5. replies（ツリーの続き）")
    見せる(頼む(client, "返信", f"{p['id']}/replies", {"fields": 基本}), 3)


if __name__ == "__main__":
    main()
