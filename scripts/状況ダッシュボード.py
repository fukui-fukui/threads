"""3地域の状況ダッシュボード（Artifact）に入れる形に、odekake-data の数字をまとめる

2026-10-16 代表（統括経由）「福井、石川、岐阜の状況を見れるダッシュボードを作って」。
毎朝の定例（8:27）で、odekake-data を取ってきてからこれを動かし、出たファイルを
ダッシュボードのデータベース（collection "regions"）に入れる。金額・割合・鍵は入れない。

  python scripts/状況ダッシュボード.py <odekake-data のフォルダ> <書き出し先>
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

地域 = {
    "fukui": {"名前": "ふくいおでかけ", "GA": "G-13WG76PCKH"},
    "ishikawa": {"名前": "いしかわおでかけ", "GA": "G-30WY9GJLB5"},
    "gifu-aichi": {"名前": "ぎふあいちおでかけ", "GA": "G-MLHCE9FXWR"},
}


def 読む(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def GAの日ごと(rows: list[dict]) -> list[dict]:
    """GA は数が 0 の日を返さないので、最初の日から最後の日まで 0 で埋める"""
    if not rows:
        return []
    by = {r["date"]: r for r in rows}
    d = date.fromisoformat(f"{min(by)[:4]}-{min(by)[4:6]}-{min(by)[6:]}")
    end = date.fromisoformat(f"{max(by)[:4]}-{max(by)[4:6]}-{max(by)[6:]}")
    出 = []
    while d <= end:
        r = by.get(d.strftime("%Y%m%d"), {})
        出.append({"日": d.isoformat(), "表示回数": r.get("screenPageViews", 0), "ユーザー数": r.get("activeUsers", 0)})
        d += timedelta(days=1)
    return 出


def まとめる(data: Path) -> dict[str, dict]:
    アクセス = 読む(data / "fukui" / "insights" / "アクセス" / "最新.json")
    出 = {}
    for key, 設定 in 地域.items():
        s = 読む(data / key / "insights" / "状況" / "最新.json")
        t = s.get("Threads", {})
        g = next((x for x in アクセス.get("GA", []) if 設定["GA"] in (x.get("計測ID") or [])), None)
        doc = {
            "名前": s.get("サイト名") or 設定["名前"],
            "アカウント": s.get("アカウント"),
            "掲載": {**(s.get("掲載") or {}), "時点": s.get("作った時刻")},
            "Threads": {
                "時点": s.get("作った時刻"),
                "7日": t.get("7日"),
                "30日": t.get("30日"),
                "日ごと": [{"日": r["日"], "views": r["views"]} for r in t.get("日ごと", [])],
                "フォロワー": t.get("フォロワー"),
                "フォロワーの推移": t.get("フォロワーの推移", []),
            },
        }
        if not s:
            doc["Threads"]["エラー"] = "まだ数字がありません"
        if g and not g.get("エラー"):
            def 二つ(x):
                return {"表示回数": (x or {}).get("screenPageViews"), "ユーザー数": (x or {}).get("activeUsers")}
            doc["GA"] = {
                "時点": アクセス.get("作った時刻") or アクセス.get("作った日"),
                "7日": 二つ(g.get("直近7日")),
                "30日": 二つ(g.get("直近30日")),
                "日ごと": GAの日ごと(g.get("日ごと30日", [])),
            }
        else:
            doc["GA"] = {"エラー": "GA の数字を読めませんでした"}
        出[key] = doc
    return 出


def main() -> None:
    data, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for key, doc in まとめる(data).items():
        (out / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        print(key, "掲載", doc["掲載"].get("件数"), "GA" if "エラー" not in doc["GA"] else "GAなし")


if __name__ == "__main__":
    main()
