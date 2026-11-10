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


def もう出ている(item: dict, uid: str) -> dict | None:
    """直近の投稿に同じキャプションがあれば、その投稿を返す（公開の返事がエラーでも、実は出ていたときに二重に出さない。
    2026-11-10：3選リールが「-1 Fatal」で4回続けて失敗した）。"""
    try:
        最近 = 呼ぶ("GET", f"{uid}/media", fields="id,caption,permalink,timestamp", limit="10").get("data", [])
    except RuntimeError:
        return None
    頭 = (item.get("caption") or "").strip()[:80]
    for m in 最近:
        if 頭 and (m.get("caption") or "").strip()[:80] == 頭:
            return {"media_id": m["id"], "permalink": m.get("permalink"), "posted_at": m.get("timestamp")}
    return None


def 出す(item: dict, uid: str) -> dict:
    if item.get("image_url"):
        # 画像1枚の投稿（2026-10-17 代表「Instagram の固定投稿を自動で出して」）
        c = 呼ぶ("POST", f"{uid}/media", image_url=item["image_url"], caption=item.get("caption", ""))
    else:
        try:
            c = 呼ぶ("POST", f"{uid}/media", media_type="REELS", video_url=item["video_url"],
                    caption=item.get("caption", ""), share_to_feed="true")
        except RuntimeError as e:
            raise RuntimeError(f"入れ物を作るところで失敗: {e}") from None
    cid = c["id"]
    print(f"入れ物を作りました（{item['id']}）。処理を待ちます")
    # 処理を待つ（最大10分。動画は時間がかかる）
    for _ in range(60):
        try:
            状態 = 呼ぶ("GET", cid, fields="status_code,status")
        except RuntimeError as e:
            raise RuntimeError(f"処理の待ちで失敗: {e}") from None
        st = 状態.get("status_code")
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"動画の処理に失敗しました（{st}・{str(状態.get('status', ''))[:200]}）")
        time.sleep(10)
    else:
        raise RuntimeError("動画の処理が10分で終わりませんでした")
    # 処理が終わってすぐの公開で「-1 Fatal」が続いた（2026-11-10）。少し待ち、同じ入れ物で公開だけを3回までやり直す
    mid = None
    for 回 in range(3):
        time.sleep(15 if 回 == 0 else 30)
        try:
            mid = 呼ぶ("POST", f"{uid}/media_publish", creation_id=cid)["id"]
            break
        except RuntimeError as e:
            最後 = e
            print(f"公開の {回 + 1} 回目で失敗（{e}）")
            既に = もう出ている(item, uid)
            if 既に:
                return 既に
    if not mid:
        raise RuntimeError(f"公開で失敗: {最後}")
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
    for item in 出すもの:
        if dry:
            print(f"[dry-run] 出しません {item['id']} {item.get('video_url') or item.get('image_url')}")
            continue
        回の鍵 = f"{item['id']}@{item['scheduled_at']}"
        失敗の数 = posted.setdefault("失敗", {}).get(回の鍵, 0)
        if 失敗の数 >= 3:
            # 同じリールを10分ごとに作り直し続けない（2026-11-10 代表「エラーのメールが来てる」）。予定を変えると、また3回試す
            print(f"::warning::{item['id']} は {失敗の数} 回失敗したので、もう試しません（ig-queue の scheduled_at を変えると、また試します）")
            continue
        try:
            既に = もう出ている(item, uid)
            if 既に:
                posted["posted"][item["id"]] = 既に
                print(f"Instagram にもう出ていました（記録だけ残します）: {item['id']} {既に.get('permalink')}")
                continue
            posted["posted"][item["id"]] = 出す(item, uid)
            print(f"Instagram に出しました: {item['id']} {posted['posted'][item['id']]['permalink']}")
        except RuntimeError as e:
            # Threads の予約投稿の流れ全体を失敗にしない（10分ごとにエラーのメールが届いた）。注記だけ残し、回数を数える
            print(f"::warning::Instagram に出せませんでした {item['id']}（{e}）")
            posted["失敗"][回の鍵] = 失敗の数 + 1
    POSTED.parent.mkdir(parents=True, exist_ok=True)
    POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
