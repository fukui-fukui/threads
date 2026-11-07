"""ネタ帳のお店の行に、出典のページにある営業時間・定休日を足す（AI を使わない）。

2026-11-07 運用部・石川：出典に営業時間があるのに投稿に書かない店が3本（日常茶飯・Cucuri・焼肉たなか）。
翌日ぶんの作成はネタ帳の行だけを見て書くので、行に無い営業時間は投稿にも入らない。
情報集めの指示でも「新店の行には営業時間を入れる」としているが、開くページの数に上限があり（石川は 11/7 から4つ）、抜けが出る。
そこで、お店の行で営業時間が無いものは、同じ日の「出典」のページ（と行の［公式: …］）を開き、店の名前が載っているページの
「営業時間」「定休日」のすぐあとの文を、そのまま行の後ろに「［営業時間: …／定休日: …（出典のページ）］」として足す。
ページの文を写すだけで、作らない。見つからなければ何もしない（同じ店は二度開かない）。

  python scripts/営業時間を足す.py [--dry-run] [--max 25]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from pathlib import Path

ネタ帳 = Path("neta/ネタ帳.md")
記録 = Path("neta/営業時間の確認.json")   # 開いた店の名前 → 結果（同じ店を何度も開かない）
_名 = re.compile(r"「([^「」]{2,40})」")
_時間あり = re.compile(r"営業|\d{1,2}[:：]\d{2}|\d{1,2}時")
_店らしい = re.compile(r"店|カフェ|バー|食堂|レストラン|ベーカリー|パン|ラーメン|そば|うどん|焼肉|寿司|鮨|喫茶|居酒屋|ビストロ|"
                     r"スイーツ|ケーキ|ソフトクリーム|ジェラート|コーヒー|珈琲|オープン|開店|リニューアル")
_催し = re.compile(r"開催|開かれ|まつり|祭り|フェス|マルシェ|展|ライトアップ|イルミ|募集|講座|体験会")
_まとめ = re.compile(r"\d+選|まとめ|一覧|特集|ランキング|名店")   # 何軒も並べた記事の行は、どの店の時間か決められないので見ない
_宿 = re.compile(r"宿|ホテル|旅館|民宿|温泉の宿")   # 宿は営業時間ではなくチェックインの時間なので見ない
_URL = re.compile(r"https?://[^\s）)」］\]<>]+")


def ページの文(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (odekake)"})
        with urllib.request.urlopen(req, timeout=20) as r:
            s = r.read(1_500_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    s = re.sub(r"(?is)<(script|style|noscript).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|dd|dt|h\d)>", "\n", s)
    t = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t　]+", " ", t)


def 抜き出す(文: str, 名: str) -> str | None:
    """名前の載っているページの「営業時間」「定休日」のあとの文。名前の近くを先に見る。"""
    型 = r"\s*".join(re.escape(c) for c in re.sub(r"\s+", "", 名))
    位置 = [m.start() for m in re.finditer(型, 文)]
    if not 位置:
        return None
    出 = {}
    for 札 in ("営業時間", "定休日"):
        候補 = [m for m in re.finditer(rf"{札}\s*[:：]?\s*(?:は)?\s*([^\n]{{2,70}})", 文)]
        if not 候補:
            continue
        m = min(候補, key=lambda m: min(abs(m.start() - p) for p in 位置))
        v = m.group(1).strip().rstrip("。").strip()
        if 札 == "営業時間" and not re.search(r"\d", v):
            continue
        出[札] = v[:70]
    if "営業時間" not in 出:
        return None
    return "／".join(f"{k}: {v}" for k, v in 出.items())


def 区切り(lines: list[str]):
    """「### 日付」ごとに、行の番号たちと出典の URL たち。"""
    塊, 今 = [], None
    for i, l in enumerate(lines):
        if l.startswith("### "):
            今 = {"行": [], "出典": []}
            塊.append(今)
        elif 今 is not None:
            if l.startswith("- http"):
                今["出典"].append(l[2:].strip())
            elif l.startswith("- "):
                今["行"].append(i)
        if l.startswith("## ") and not l.startswith("## 書き足す場所"):
            今 = None
    return 塊


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=25)
    a = ap.parse_args()
    lines = ネタ帳.read_text(encoding="utf-8").split("\n")
    済み = json.loads(記録.read_text(encoding="utf-8")) if 記録.exists() else {}
    開いた: dict[str, str] = {}
    足した = 開いた数 = 0
    for 塊 in 区切り(lines):
        for i in 塊["行"]:
            l = lines[i]
            本文 = l.split("（→")[0]
            if _時間あり.search(本文) or "営業時間:" in l or _催し.search(本文) or _まとめ.search(本文):
                continue
            # 店の名前は、店らしい言葉がすぐ前後にある「」だけ（「カフェ「X」」「「X」がオープン」）。品物や言葉の「」をとらない
            名 = None
            for m in _名.finditer(本文):
                近く = 本文[max(0, m.start() - 12): m.start()] + 本文[m.end(): m.end() + 12]   # 名前そのものは見ない（「にしんの寿司」の寿司）
                if (_店らしい.search(近く) or _店らしい.search(m.group(1)) and re.search(r"^[がはでに、（(]|オープン|開店", 本文[m.end(): m.end() + 6])) \
                        and not _宿.search(本文) and not re.search(r"コーナー|リニューアル|メニュー|限定", m.group(1)):
                    名 = m.group(1)
                    break
            if not 名 or 名 in 済み:
                continue
            if 開いた数 >= a.max:
                break
            urls = [u for u in _URL.findall(l) if "instagram.com" not in u] + [u for u in 塊["出典"] if "instagram.com" not in u]
            見つけた = None
            for u in dict.fromkeys(urls):
                if u not in 開いた:
                    開いた[u] = ページの文(u)
                    開いた数 += 1
                v = 抜き出す(開いた[u], 名)
                if v:
                    見つけた = (v, u)
                    break
            済み[名] = 見つけた[1] if 見つけた else ""
            if 見つけた:
                lines[i] = l.rstrip() + f" ［{見つけた[0]}（{見つけた[1]}）］"
                足した += 1
                print(f"足した：「{名}」 {見つけた[0]}")
    print(f"お店の行に営業時間を {足した} 件足しました（開いたページ {開いた数}）")
    if not a.dry_run:
        ネタ帳.write_text("\n".join(lines), encoding="utf-8")
        記録.write_text(json.dumps(済み, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
