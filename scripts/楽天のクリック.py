"""楽天のリンクが押された回数を、アカウントごと・投稿ごとにまとめて、ダッシュボード（collection "clicks"）に入れる形にする。

2026-11-07 代表（統括経由）：楽天のリンクをアカウント別に分けて数えたい。楽天アフィリエイトの管理画面では
短いリンクごとのクリック数は見られない（代表「分けれない」）。転送ページをはさむ案（b）は、楽天アフィリエイトの
ガイドライン（リンク先URLの変更・楽天以外の短縮URLの禁止）に当たるおそれがあるのでやめ、
Threads のインサイト API の clicks（リンクごとの回数）を使う（統括 11/7「a で進めて」）。

読むもの（どれも毎日の作業がすでに残しているもの。AI は使わない・個人の情報は無い）
  福井・石川・ぎふあいち … odekake-data/<地域>/insights/アフィリのクリック.jsonl（scripts/アフィリの検証.py）
  yu                     … yu のリポジトリの insights/リンクのクリック.jsonl（scripts/リンクのクリック.py）
  投稿                   … 各リポジトリの posts/queue.jsonl

その日のクリックは「その日までに出た、そのリンクを使ったいちばん新しい投稿」に数える（アフィリの検証.py と同じ）。
クリックは Threads の中でリンクが押された回数。楽天のレポートの数え方とは違う。

  python scripts/楽天のクリック.py <odekake-data> <書き出し先> --fukui … --ishikawa … --gifuaichi … --yu …
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

楽天 = re.compile(r"https?://(?:a\.r10\.to|hb\.afl\.rakuten\.co\.jp|[\w.-]*rakuten\.co\.jp)/[^\s）)」]*")


def 正規化(u: str) -> str:
    """同じリンクの書き方ちがいをそろえる。楽天のリンクは、投稿では「…/?pc=」、インサイトでは「…?pc=」で返ってくる
    （石川・ぎふあいちの hb.afl のリンクが投稿に結びつかなかった）。pc（行き先）があればそれで見る。"""
    from urllib.parse import parse_qs, unquote, urlsplit
    u = u.strip().rstrip("\\n").strip()
    q = parse_qs(urlsplit(u).query)
    if q.get("pc"):
        return unquote(q["pc"][0]).rstrip("/")
    return unquote(u).replace("/?", "?").rstrip("/")


def 種類(note: str, url: str) -> str:
    n = note or ""
    if "ふるさと納税" in n:
        return "ふるさと納税"
    if "宿" in n or "楽天トラベル" in n or "クーポン" in n or "travel" in url:
        return "楽天トラベル"
    if "美容" in n:
        return "美容"
    return "その他の楽天"


def 最後の記録(p: Path) -> dict:
    try:
        rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    except FileNotFoundError:
        return {}
    return rows[-1] if rows else {}


def 投稿たち(repo: Path) -> list[dict]:
    出 = []
    q = repo / "posts" / "queue.jsonl"
    if not q.exists():
        return 出
    for l in q.read_text(encoding="utf-8").splitlines():
        if not l.strip().startswith("{"):
            continue
        e = json.loads(l)
        文 = "\n".join([str(e.get("text") or ""), *[str(t) for t in (e.get("thread") or [])],
                       *[str(u) for u in (e.get("thread_links") or []) if u]])
        リンク = {正規化(u) for u in 楽天.findall(文)}
        if リンク and e.get("scheduled_at"):
            出.append({"日": e["scheduled_at"][:10], "時": int(e["scheduled_at"][11:13]), "id": e.get("id"),
                      "1行目": next((x for x in str(e.get("text") or "").splitlines() if x.strip()), "")[:40],
                      "note": e.get("note") or "", "リンク": リンク})
    出.sort(key=lambda p: (p["日"], p["時"]))
    return 出


def まとめる(名前: str, 記録: dict, 投稿: list[dict]) -> dict:
    if not 記録:
        return {"名前": 名前, "エラー": "まだクリックの記録がありません"}
    取った日 = date.fromisoformat(記録["取った日"])
    七日前 = (取った日 - timedelta(days=7)).isoformat()
    期間 = {"7日": defaultdict(int), "28日": defaultdict(int)}
    日ごと = defaultdict(int)
    投稿の回 = defaultdict(int)
    for 日, 回 in sorted((記録.get("日ごと") or {}).items()):
        for u, c in 回.items():
            if not c or not 楽天.match(u):
                continue
            候補 = [p for p in 投稿 if 正規化(u) in p["リンク"] and p["日"] <= 日]
            p = 候補[-1] if 候補 else None
            k = 種類(p["note"] if p else "", u)
            期間["28日"][k] += c
            if 日 >= 七日前:
                期間["7日"][k] += c
            日ごと[日] += c
            if p:
                投稿の回[p["id"]] += c
    by_id = {p["id"]: p for p in 投稿}
    上位 = sorted(投稿の回.items(), key=lambda x: -x[1])[:10]
    日 = 取った日 - timedelta(days=28)
    並び = []
    while 日 < 取った日:
        並び.append({"日": 日.isoformat(), "回": 日ごと.get(日.isoformat(), 0)})
        日 += timedelta(days=1)
    return {
        "名前": 名前,
        "時点": 記録["取った日"],
        "7日": {**期間["7日"], "合計": sum(期間["7日"].values())},
        "28日": {**期間["28日"], "合計": sum(期間["28日"].values())},
        "日ごと": 並び,
        "投稿": [{"日": by_id[i]["日"], "時": by_id[i]["時"], "1行目": by_id[i]["1行目"],
                "種類": 種類(by_id[i]["note"], next(iter(by_id[i]["リンク"]))), "回": c} for i, c in 上位],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("out")
    ap.add_argument("--fukui", required=True)
    ap.add_argument("--ishikawa", required=True)
    ap.add_argument("--gifuaichi", required=True)
    ap.add_argument("--yu", required=True)
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    先 = {
        "yu": ("yu", Path(a.yu) / "insights" / "リンクのクリック.jsonl", Path(a.yu)),
        "fukui": ("ふくいおでかけ", data / "fukui" / "insights" / "アフィリのクリック.jsonl", Path(a.fukui)),
        "ishikawa": ("いしかわおでかけ", data / "ishikawa" / "insights" / "アフィリのクリック.jsonl", Path(a.ishikawa)),
        "gifu-aichi": ("ぎふあいちおでかけ", data / "gifu-aichi" / "insights" / "アフィリのクリック.jsonl", Path(a.gifuaichi)),
    }
    for key, (名前, 記録, repo) in 先.items():
        doc = まとめる(名前, 最後の記録(記録), 投稿たち(repo))
        (out / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        print(key, "7日", doc.get("7日"), "28日", doc.get("28日"), doc.get("エラー", ""))


if __name__ == "__main__":
    main()
