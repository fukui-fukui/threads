"""おでかけ ダッシュボードの「費用」タブに入れる形に、odekake-data の AI 使用量をまとめる

2026-10-18 代表（統括経由）「おでかけダッシュボードに API 使用料・量を入れて」。
ダッシュボードは代表しか開けないので金額を載せてよい（代表）。ただし、このスクリプトは
金額を公開のログやリポジトリに書かない（出力は引数で渡したフォルダの JSON だけ。標準出力には件数だけ）。

  python scripts/費用ダッシュボード.py <odekake-data のフォルダ> <書き出し先> [yu の usage.jsonl]

yu（yu-fukui/threads_yu-fukui）は公開リポジトリなので、記録に金額が無い（トークン数だけ）。
3つめの引数で yu の state/usage.jsonl を渡すと、ここで単価から金額を計算して足す（2026-10-19 代表「おすすめの設定で」）。

予算は 予算.json（本体は「名」の予算。2026-10-19 から福井 $40。「別に数える」の地域（石川・ぎふあいち）はそれぞれ別）。
定期（cron-job.org・schedule）と手動・追加（Run workflow など）を分けて足す（記録の「起動」。
2026-10-18 代表「定期実行分と、私の指示や追加で必要な対応をした分と分けて計れませんか？」）。
「起動」の無い古い行は「不明」に入れる。
"""
from __future__ import annotations

import json
import sys

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import 使用量  # noqa: E402  単価（金額の無い記録の計算に使う）

JST = timezone(timedelta(hours=9))
地域 = [
    ("fukui", "ふくいおでかけ"),
    ("ishikawa", "いしかわおでかけ"),
    ("gifu-aichi", "ぎふあいちおでかけ"),
]
# 記録があれば足す（2026-10-18 時点では odekake-data に使用量の記録が無い）
ほか = [("ekimae", "ふくいエキマエ"), ("yu", "yu")]


def 読む(p: Path | None) -> list[dict]:
    if not p or not p.exists():
        return []
    出 = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("ドル") is None:
            # 金額の無い記録（yu）は単価から計算する
            r["ドル"] = 使用量.ドル(r.get("モデル") or "", {"input_tokens": r.get("入力") or 0, "output_tokens": r.get("出力") or 0},
                               int(r.get("検索") or 0))
        出.append(r)
    return 出


def 起動(r: dict) -> str:
    return r.get("起動") if r.get("起動") in ("定期", "手動") else "不明"


def 分ける(行たち: list[dict]) -> dict:
    出 = {"定期": 0.0, "手動": 0.0, "不明": 0.0}
    for r in 行たち:
        出[起動(r)] += float(r.get("ドル") or 0)
    if not 出["不明"]:
        del 出["不明"]
    return {k: round(v, 2) for k, v in 出.items()}


def まとめる(data: Path, 予算設定: dict, 今: datetime, 場所: dict[str, Path] | None = None) -> dict:
    月 = 今.strftime("%Y-%m")
    別 = {b["置き場"]: b for b in 予算設定.get("別に数える", [])}
    本 = 予算設定.get("名") or "福井＋石川"  # 予算.json の本体の予算の名前（2026-10-19 から「福井」）
    地域たち = []
    for key, 名 in 地域 + ほか:
        元 = (場所 or {}).get(key) or data / key / "state" / "usage.jsonl"
        行たち = [r for r in 読む(元) if str(r.get("時刻", "")).startswith(月)]
        if not 行たち and (key, 名) in ほか:
            continue
        日 = defaultdict(float)
        日の手動 = defaultdict(float)
        仕事 = defaultdict(lambda: {"回数": 0, "ドル": 0.0, "入力": 0, "出力": 0, "検索": 0, "モデル": set(), "起動": []})
        for r in 行たち:
            日[r["時刻"][:10]] += float(r.get("ドル") or 0)
            if 起動(r) == "手動":
                日の手動[r["時刻"][:10]] += float(r.get("ドル") or 0)
            w = 仕事[r.get("何") or "その他"]
            w["回数"] += 1
            w["ドル"] += float(r.get("ドル") or 0)
            w["起動"].append(r)
            for k in ("入力", "出力", "検索"):
                w[k] += int(r.get(k) or 0)
            if r.get("モデル"):
                w["モデル"].add(r["モデル"])
        地域たち.append({
            "key": key, "名": 名,
            # 予算の無いもの（エキマエ・yu）は、それぞれ自分の名前のグループにする
            "グループ": 別[key]["名"] if key in 別 else (本 if (key, 名) in 地域 else 名),
            "ドル": round(sum(日.values()), 2),
            "起動別": 分ける(行たち),
            "回数": len(行たち),
            "入力": sum(int(r.get("入力") or 0) for r in 行たち),
            "出力": sum(int(r.get("出力") or 0) for r in 行たち),
            "検索": sum(int(r.get("検索") or 0) for r in 行たち),
            "日ごと": [{"日": d, "ドル": round(日[d], 3), "手動": round(日の手動[d], 3)} for d in sorted(日)],
            "仕事": sorted(({"何": k, **{**{k2: x for k2, x in v.items() if k2 != "起動"}, "ドル": round(v["ドル"], 2), "モデル": "・".join(sorted(v["モデル"])),
                                                 "起動別": 分ける(v["起動"]),
                                                 "手動回数": sum(1 for r in v["起動"] if 起動(r) == "手動")}}
                          for k, v in 仕事.items()), key=lambda x: -x["ドル"]),
        })
    グループ = []
    予算たち = [(本, 予算設定.get("月の予算ドル"))] + [(b["名"], b.get("月の予算ドル")) for b in 別.values()]
    予算たち += [(r["名"], None) for r in 地域たち if r["グループ"] not in {n for n, _ in 予算たち}]
    for 名, 予算 in 予算たち:
        ドル = round(sum(r["ドル"] for r in 地域たち if r["グループ"] == 名), 2)
        起 = defaultdict(float)
        for r in 地域たち:
            if r["グループ"] == 名:
                for k, v in r["起動別"].items():
                    起[k] += v
        グループ.append({"名": 名, "予算": 予算, "ドル": ドル, "割合": round(ドル / 予算 * 100, 1) if 予算 else None,
                       "起動別": {k: round(v, 2) for k, v in 起.items()}})
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
    場所 = {"yu": Path(sys.argv[3])} if len(sys.argv) > 3 else {}
    予算設定 = json.loads(Path("予算.json").read_text(encoding="utf-8"))
    d = まとめる(data, 予算設定, datetime.now(JST), 場所)
    out.mkdir(parents=True, exist_ok=True)
    (out / "今月.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    # 金額は出さない（公開のログに残らないように）
    print(f"{d['月']}：{len(d['地域'])} 地域をまとめました（{out / '今月.json'}）")


if __name__ == "__main__":
    main()
