"""サイトの掲載件数と Threads の数字をまとめて、insights/状況/最新.json に残す（3地域の状況ダッシュボード用）

2026-10-16 代表（統括経由）「福井、石川、岐阜の状況を見れるダッシュボードを作って。
サイトの掲載件数、アクセス数、Threadsの再生数、閲覧者数」。
- 掲載件数：docs/data.json の件数（催し・スポット・話題の内訳つき）
- Threads の再生数：直近30日に出した投稿ごとの views を、出した日ごとに足す（今の時点の数）
- 閲覧者数（ユニークの人数）は Threads の API に無い。代わりにフォロワー数を毎日 フォロワー.jsonl に足して推移にする
- サイトのアクセス数（GA）は アクセス解析.py が 福井の置き場の insights/アクセス/最新.json に3地域ぶん書く
書き出しは非公開の置き場（odekake-data）だけ。数字は公開のログに出さない。

環境変数:
  THREADS_ACCESS_TOKEN … 投稿用のトークン（読むだけに使う）
  OUT_DIR              … 書き出し先（既定 insights/状況）
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://graph.threads.net/v1.0"
JST = timezone(timedelta(hours=9))
指標 = ("views", "likes", "replies", "reposts", "quotes")
日数 = 30


def get(path: str, **params) -> dict:
    params["access_token"] = os.environ["THREADS_ACCESS_TOKEN"]
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        try:
            err = json.load(e).get("error", {})
        except Exception:  # noqa: BLE001
            err = {}
        return {"error": {"code": err.get("code"), "status": e.code}}
    except Exception:  # noqa: BLE001
        return {"error": {"code": None, "status": None}}


def 値(item: dict) -> int:
    if "total_value" in item:
        return int(item["total_value"].get("value") or 0)
    vals = item.get("values") or [{}]
    return int(vals[0].get("value") or 0)


def 掲載件数(path: Path = Path("docs/data.json")) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    items = d.get("items", [])
    return {
        "件数": len(items),
        "内訳": {k: sum(1 for i in items if i.get("kind") == k) for k in ("催し", "スポット", "話題")},
        "サイトの更新": d.get("updated"),
    }


def 出した投稿(今日, path: Path = Path("state/posted.json")) -> list[tuple[str, str]]:
    """直近 日数 日（今日を入れない）に出した投稿の（JST の日, 投稿 ID）"""
    try:
        posted = json.loads(path.read_text(encoding="utf-8")).get("posted", {})
    except (FileNotFoundError, ValueError):
        return []
    始め = 今日 - timedelta(days=日数)
    出 = []
    for r in posted.values():
        pid, at = r.get("post_id"), r.get("posted_at")
        if not pid or not at:
            continue
        日 = datetime.fromisoformat(at).astimezone(JST).date()
        if 始め <= 日 < 今日:
            出.append((日.isoformat(), str(pid)))
    return 出


def 日ごとに足す(投稿: list[tuple[str, str]], 数たち: dict[str, dict], 今日) -> list[dict]:
    行 = {(今日 - timedelta(days=i)).isoformat(): {"日": (今日 - timedelta(days=i)).isoformat(), "投稿": 0,
          **{m: 0 for m in 指標}} for i in range(日数, 0, -1)}
    for 日, pid in 投稿:
        r = 行.get(日)
        if r is None or pid not in 数たち:
            continue
        r["投稿"] += 1
        for m in 指標:
            r[m] += 数たち[pid].get(m, 0)
    return list(行.values())


def 合計(日ごと: list[dict], n: int) -> dict:
    return {k: sum(r[k] for r in 日ごと[-n:]) for k in ("投稿", *指標)}


def アカウントのviews(今日) -> list[dict] | None:
    """アカウント全体の views を日ごとに（直近 日数 日、今日を入れない）。
    ドキュメントでは「プロフィールが見られた回数」だが、アプリのインサイトの「再生数」と同じかを比べるために取る
    （2026-10-17 統括：何日か比べて、同じならダッシュボードの再生数をアプリと同じ数え方にそろえる）"""
    始め = datetime.combine(今日 - timedelta(days=日数), datetime.min.time(), JST)
    終わり = datetime.combine(今日, datetime.min.time(), JST)
    d = get("me/threads_insights", metric="views", since=int(始め.timestamp()), until=int(終わり.timestamp()))
    if "error" in d:
        return None
    出 = {}
    for item in d.get("data", []):
        for v in item.get("values") or []:
            t = v.get("end_time")
            if not t:
                continue
            # end_time はその日の終わり（次の日の 0 時、太平洋時間のことがある）。1秒前の日本の日付にする
            日 = (datetime.fromisoformat(t.replace("+0000", "+00:00")) - timedelta(seconds=1)).astimezone(JST).date()
            出[日.isoformat()] = 出.get(日.isoformat(), 0) + int(v.get("value") or 0)
    return [{"日": k, "views": 出[k]} for k in sorted(出)]


def フォロワーを足す(path: Path, 日: str, 数: int | None) -> list[dict]:
    行 = {}
    if path.exists():
        for x in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(x)
                行[r["日"]] = r
            except (ValueError, KeyError):
                continue
    if 数 is not None:
        行[日] = {"日": 日, "フォロワー": 数}
    並び = [行[k] for k in sorted(行)]
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in 並び), encoding="utf-8")
    return 並び


def main() -> None:
    if not os.environ.get("THREADS_ACCESS_TOKEN"):
        sys.exit("THREADS_ACCESS_TOKEN がありません")
    今 = datetime.now(JST)
    今日 = 今.date()
    out = Path(os.environ.get("OUT_DIR", "insights/状況"))
    out.mkdir(parents=True, exist_ok=True)
    地域 = json.loads(Path("region.json").read_text(encoding="utf-8"))

    投稿 = 出した投稿(今日)
    数たち, 取れない = {}, 0
    for _, pid in 投稿:
        d = get(f"{pid}/insights", metric=",".join(指標))
        if "error" in d:
            取れない += 1
            if d["error"].get("code") in (10, 190):
                print("::error::Threads のトークンが使えません（取り直しが要ります）")
                sys.exit(1)
            continue
        数たち[pid] = {i.get("name"): 値(i) for i in d.get("data", [])}
    日ごと = 日ごとに足す(投稿, 数たち, 今日)

    全体 = アカウントのviews(今日)

    fc = get("me/threads_insights", metric="followers_count")
    フォロワー = next((値(i) for i in fc.get("data", [])), None) if "error" not in fc else None
    推移 = フォロワーを足す(out / "フォロワー.jsonl", 今日.isoformat(), フォロワー)

    結果 = {
        "サイト名": 地域.get("サイト名"),
        "アカウント": 地域.get("アカウント"),
        "作った時刻": 今.isoformat(timespec="minutes"),
        "掲載": 掲載件数(),
        "Threads": {
            "説明": "直近30日（昨日まで）に出した投稿の、今の時点の数を、出した日ごとに足したもの",
            "日ごと": 日ごと,
            "7日": 合計(日ごと, 7),
            "30日": 合計(日ごと, 30),
            "取れなかった投稿": 取れない,
            "フォロワー": フォロワー,
            "アカウントのviews": None if 全体 is None else {
                "説明": "アカウント全体の views（API の threads_insights）。アプリの再生数と同じか比べるため",
                "日ごと": 全体,
                "7日": sum(r["views"] for r in 全体[-7:]),
                "30日": sum(r["views"] for r in 全体),
            },
            "フォロワーの推移": 推移[-日数:],
        },
    }
    (out / "最新.json").write_text(json.dumps(結果, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"書き出しました（投稿 {len(投稿)} 本、取れなかった {取れない} 本。数字は公開のログに出しません）")


if __name__ == "__main__":
    main()
