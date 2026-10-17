"""Instagram（@fukui._fukui）にリール動画を出す。posts/ig-queue.jsonl の予約時刻が来たものだけ。

2026-10-17 代表（統括経由）「リール動画を Threads と Instagram の両方に自動で出したい」。
- 公式の Graph API（Facebook ログインの方式）：/{ig-user-id}/media（REELS）→ 処理を待つ → /media_publish
- 動画はサイトの docs/reel/ に置いた公開 URL（https://odekake.fukui-fukui.com/reel/...）
- 出したものは state/ig-posted.json に残す。同じ id は二度出さない
- 鍵の値はログに出さない

posts/ig-queue.jsonl の1行：
  {"id": "ig-...", "scheduled_at": "2026-10-23T18:00:00+09:00", "video_url": "https://...mp4", "caption": "..."}
  画像1枚なら video_url の代わりに "image_url": "https://...jpg"

環境変数: IG_USER_ID・IG_ACCESS_TOKEN（Secrets）、DRY_RUN=true なら出さない
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://graph.facebook.com/v26.0"
QUEUE = Path("posts/ig-queue.jsonl")
POSTED = Path("state/ig-posted.json")


def 呼ぶ(method: str, path: str, **params) -> dict:
    key = os.environ["IG_ACCESS_TOKEN"]
    params["access_token"] = key
    data = urllib.parse.urlencode(params)
    url = f"{API}/{path}"
    req = urllib.request.Request(url + ("?" + data if method == "GET" else ""),
                                 data=data.encode() if method == "POST" else None, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
        except Exception:  # noqa: BLE001
            err = {}
        文 = f"{err.get('code', e.code)} {str(err.get('message', ''))[:200]}".replace(key, "＊＊＊")
        raise RuntimeError(文) from None


def 読む_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    return [json.loads(l) for l in QUEUE.read_text(encoding="utf-8").splitlines() if l.strip()]


def 出す(item: dict, uid: str) -> dict:
    if item.get("image_url"):
        # 画像1枚の投稿（2026-10-17 代表「Instagram の固定投稿を自動で出して」）
        c = 呼ぶ("POST", f"{uid}/media", image_url=item["image_url"], caption=item.get("caption", ""))
    else:
        c = 呼ぶ("POST", f"{uid}/media", media_type="REELS", video_url=item["video_url"],
                caption=item.get("caption", ""), share_to_feed="true")
    cid = c["id"]
    # 処理を待つ（最大10分。動画は時間がかかる）
    for _ in range(60):
        st = 呼ぶ("GET", cid, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"動画の処理に失敗しました（{st}）")
        time.sleep(10)
    else:
        raise RuntimeError("動画の処理が10分で終わりませんでした")
    mid = 呼ぶ("POST", f"{uid}/media_publish", creation_id=cid)["id"]
    link = 呼ぶ("GET", mid, fields="permalink").get("permalink")
    return {"media_id": mid, "permalink": link, "posted_at": datetime.now(timezone.utc).isoformat()}


def main() -> None:
    uid = os.environ.get("IG_USER_ID", "").strip()
    if not uid or not os.environ.get("IG_ACCESS_TOKEN", "").strip():
        print("IG_USER_ID / IG_ACCESS_TOKEN が無いので、Instagram には出しません")
        return
    dry = os.environ.get("DRY_RUN", "").lower() == "true"
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {"posted": {}}
    now = datetime.now(timezone.utc)
    出すもの = [i for i in 読む_queue()
             if i["id"] not in posted["posted"] and datetime.fromisoformat(i["scheduled_at"]) <= now]
    if not 出すもの:
        return
    # 鍵が別のアカウント（yu など）につながっていたら出さない（2026-10-17、最初の鍵が yu._.fukui につながっていた）
    出す先 = (json.loads(Path("region.json").read_text(encoding="utf-8")).get("インスタ") or "").lstrip("@")
    try:
        名前 = 呼ぶ("GET", uid, fields="username").get("username")
    except RuntimeError as e:
        print(f"::error::Instagram のアカウントを読めません（{e}）")
        sys.exit(1)
    if not 出す先 or 名前 != 出す先:
        print(f"::error::鍵のアカウント（{名前}）が region.json の「インスタ」（{出す先 or '未設定'}）とちがうので、出しません")
        sys.exit(1)
    失敗 = False
    for item in 出すもの:
        if dry:
            print(f"[dry-run] 出しません {item['id']} {item.get('video_url') or item.get('image_url')}")
            continue
        try:
            posted["posted"][item["id"]] = 出す(item, uid)
            print(f"Instagram に出しました: {item['id']} {posted['posted'][item['id']]['permalink']}")
        except RuntimeError as e:
            print(f"::error::Instagram に出せませんでした {item['id']}（{e}）")
            失敗 = True
    POSTED.parent.mkdir(parents=True, exist_ok=True)
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if 失敗:
        sys.exit(1)


if __name__ == "__main__":
    main()
