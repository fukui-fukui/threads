"""おでかけ ダッシュボードの「費用」タブに入れる形に、odekake-data の AI 使用量をまとめる

2026-10-18 代表（統括経由）「おでかけダッシュボードに API 使用料・量を入れて」。
ダッシュボードは代表しか開けないので金額を載せてよい（代表）。ただし、このスクリプトは
金額を公開のログやリポジトリに書かない（出力は引数で渡したフォルダの JSON だけ。標準出力には件数だけ）。

  python scripts/費用ダッシュボード.py <odekake-data のフォルダ> <書き出し先>

予算は 予算.json（福井＋石川で1つ、「別に数える」の地域は別）。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
地域 = [
    ("fukui", "ふくいおでかけ"),
    ("ishikawa", "いしかわおでかけ"),
    ("gifu-aichi", "ぎふあいちおでかけ"),
]
# 記録があれば足す（2026-10-18 時点では odekake-data に使用量の記録が無い）
ほか = [("ekimae", "ふくいエキマエ"), ("yu", "yu")]


def 読む(p: Path) -> list[dict]:
    if not p.exists():
        return []
    出 = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            出.append(json.loads(l))
        except ValueError:
            continue
    return 出


def まとめる(data: Path, 予算設定: dict, 今: datetime) -> dict:
    月 = 今.strftime("%Y-%m")
    別 = {b["置き場"]: b for b in 予算設定.get("別に数える", [])}
    地域たち = []
    for key, 名 in 地域 + ほか:
        行たち = [r for r in 読む(data / key / "state" / "usage.jsonl") if str(r.get("時刻", "")).startswith(月)]
        if not 行たち and (key, 名) in ほか:
            continue
        日 = defaultdict(float)
        仕事 = defaultdict(lambda: {"回数": 0, "ドル": 0.0, "入力": 0, "出力": 0, "検索": 0, "モデル": set()})
        for r in 行たち:
            日[r["時刻"][:10]] += float(r.get("ドル") or 0)
            w = 仕事[r.get("何") or "その他"]
            w["回数"] += 1
            w["ドル"] += float(r.get("ドル") or 0)
            for k in ("入力", "出力", "検索"):
                w[k] += int(r.get(k) or 0)
            if r.get("モデル"):
                w["モデル"].add(r["モデル"])
        地域たち.append({
            "key": key, "名": 名, "グループ": 別[key]["名"] if key in 別 else "福井＋石川",
            "ドル": round(sum(日.values()), 2),
            "回数": len(行たち),
            "入力": sum(int(r.get("入力") or 0) for r in 行たち),
            "出力": sum(int(r.get("出力") or 0) for r in 行たち),
            "検索": sum(int(r.get("検索") or 0) for r in 行たち),
            "日ごと": [{"日": d, "ドル": round(日[d], 3)} for d in sorted(日)],
            "仕事": sorted(({"何": k, **{**v, "ドル": round(v["ドル"], 2), "モデル": "・".join(sorted(v["モデル"]))}}
                          for k, v in 仕事.items()), key=lambda x: -x["ドル"]),
        })
    グループ = []
    for 名, 予算 in [("福井＋石川", 予算設定.get("月の予算ドル"))] + [(b["名"], b.get("月の予算ドル")) for b in 別.values()]:
        ドル = round(sum(r["ドル"] for r in 地域たち if r["グループ"] == 名), 2)
        グループ.append({"名": 名, "予算": 予算, "ドル": ドル, "割合": round(ドル / 予算 * 100, 1) if 予算 else None})
    return {
        "月": 月,
        "時点": 今.isoformat(timespec="minutes"),
        "グループ": グループ,
        "地域": 地域たち,
        "記録なし": [名 for key, 名 in ほか if key not in {r["key"] for r in 地域たち}],
        "注": "金額は API の使用量から見積もった概算（請求と少しずれることがあります）",
    }


def main() -> None:
    data, out = Path(sys.argv[1]), Path(sys.argv[2])
    予算設定 = json.loads(Path("予算.json").read_text(encoding="utf-8"))
    d = まとめる(data, 予算設定, datetime.now(JST))
    out.mkdir(parents=True, exist_ok=True)
    (out / "今月.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    # 金額は出さない（公開のログに残らないように）
    print(f"{d['月']}：{len(d['地域'])} 地域をまとめました（{out / '今月.json'}）")


if __name__ == "__main__":
    main()
