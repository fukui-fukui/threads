"""ネタ帳から、おでかけサイト用のデータを作る。

neta/ネタ帳.md の「書き足す場所」にある箇条書きを 1 件ずつ読み、
日付・エリア・種類・出典を取り出して docs/odekake/data.json に書き出す。
サイト（docs/odekake/index.html）はこの JSON を読むだけ。

    python scripts/おでかけ.py            # 書き出す
    python scripts/おでかけ.py --check    # 書き出さずに件数だけ見る

日付の読み取りは本文の書き方に頼った推測なので、読めなかったものは
「日付なし」として残す（捨てない）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NETA = ROOT / "neta" / "ネタ帳.md"
OUT = ROOT / "docs" / "odekake" / "data.json"

# 地名・施設名 → 市町。本文の中でいちばん前に出てくるものを採る。
AREAS = [
    ("県立美術館", "福井市"), ("ふくい工芸舎", "福井市"), ("自然保護センター", "大野市"),
    ("恐竜博物館", "勝山市"), ("ディノパーク", "勝山市"), ("県立歴史博物館", "福井市"),
    ("フェニックスプラザ", "福井市"), ("フェアモール", "福井市"), ("サンドーム", "鯖江市"),
    ("越前陶芸村", "越前町"), ("道の駅越前", "越前町"),
    ("三国", "坂井市"), ("丸岡", "坂井市"), ("春江", "坂井市"),
    ("美山", "福井市"), ("一乗谷", "福井市"), ("ハピテラス", "福井市"),
    ("福井駅", "福井市"), ("足羽山", "福井市"), ("越前海岸", "越前町"),
    ("南越前町", "南越前町"), ("越前町", "越前町"), ("永平寺町", "永平寺町"),
    ("永平寺", "永平寺町"), ("池田町", "池田町"), ("美浜町", "美浜町"),
    ("若狭町", "若狭町"), ("高浜町", "高浜町"), ("おおい町", "おおい町"),
    ("福井市", "福井市"), ("坂井市", "坂井市"), ("あわら", "あわら市"),
    ("大野", "大野市"), ("勝山", "勝山市"), ("鯖江", "鯖江市"),
    ("越前市", "越前市"), ("敦賀", "敦賀市"), ("小浜", "小浜市"),
]

# 嶺北・嶺南の区分（サイトの絞り込みで使う）
REINAN = {"敦賀市", "小浜市", "美浜町", "若狭町", "高浜町", "おおい町"}

SPOT_WORDS = ("オープン", "開業", "新店", "グランドオープン", "リニューアル", "出店")
EVENT_WORDS = ("開催", "まつり", "祭", "フェス", "展", "イベント", "マルシェ",
               "フェア", "ツアー", "体験", "募集", "公開", "ライブ", "開館")

_MD = r"(\d{1,2})/(\d{1,2})(?:\s*\([月火水木金土日祝・]+\))?"
# 9/26-10/12、10/3-4、9/10〜11/3 のような期間
RANGE = re.compile(_MD + r"\s*[-〜～－–]\s*(?:(\d{1,2})/)?(\d{1,2})(?!\d)")
SINGLE = re.compile(_MD)
JP_DATE = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")


def _year_for(month: int, base: date) -> int:
    """書いた日から見て、月だけの日付が何年のことかを決める。"""
    if month - base.month > 6:
        return base.year - 1
    if base.month - month > 6:
        return base.year + 1
    return base.year


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_dates(text: str, base: date) -> tuple[date | None, date | None]:
    """本文から (始まり, 終わり) を読む。読めなければ (None, None)。"""
    found: list[date] = []

    m = RANGE.search(text)
    if m:
        m1, d1, m2, d2 = m.group(1), m.group(2), m.group(3), m.group(4)
        start = _mk(_year_for(int(m1), base), int(m1), int(d1))
        end_month = int(m2) if m2 else int(m1)
        end = _mk(_year_for(end_month, base), end_month, int(d2))
        if start and end and end < start:
            end = _mk(end.year + 1, end.month, end.day)
        if start and end:
            return start, end

    for m in SINGLE.finditer(text):
        dt = _mk(_year_for(int(m.group(1)), base), int(m.group(1)), int(m.group(2)))
        if dt:
            found.append(dt)
    if not found:
        for m in JP_DATE.finditer(text):
            y = int(m.group(1)) if m.group(1) else _year_for(int(m.group(2)), base)
            dt = _mk(y, int(m.group(2)), int(m.group(3)))
            if dt:
                found.append(dt)
    if not found:
        return None, None
    # 9/25・10/2・10/9 のように並んでいるときは、最初から最後までを期間とみなす
    return min(found), max(found)


def guess_area(text: str) -> str | None:
    best: tuple[int, int, str] | None = None
    for word, area in AREAS:
        pos = text.find(word)
        if pos < 0:
            continue
        # 前に出てくるもの、同じ位置なら長い語（南越前町 > 越前町）を採る
        key = (pos, -len(word), area)
        if best is None or key < best:
            best = key
    return best[2] if best else None


def guess_kind(text: str) -> str:
    head = text[:80]
    if any(w in head for w in SPOT_WORDS) and not re.search(r"開催|まつり|フェス", head):
        return "スポット"
    if any(w in text for w in EVENT_WORDS):
        return "催し"
    return "話題"


def split_note(line: str) -> tuple[str, str]:
    """「本文（→ ひとこと）」を本文とひとことに分ける。"""
    m = re.search(r"（→\s*(.+?)）\s*$", line)
    if not m:
        return line.strip(), ""
    return line[: m.start()].strip(), m.group(1).strip()


def parse_neta(md: str) -> list[dict]:
    """ネタ帳の「書き足す場所」から項目を取り出す。"""
    items: list[dict] = []
    section = md.split("## 書き足す場所", 1)
    if len(section) < 2:
        return items
    body = re.split(r"\n## ", section[1], maxsplit=1)[0]

    for block in re.split(r"\n(?=### )", body):
        head = re.match(r"### (\d{4})-(\d{2})-(\d{2})", block)
        if not head:
            continue
        written = date(int(head.group(1)), int(head.group(2)), int(head.group(3)))
        main, _, rest = block.partition("<details>")
        bullets = [ln[2:].strip() for ln in main.splitlines() if ln.startswith("- ")]
        sources = re.findall(r"^- (https?://\S+)", rest, flags=re.M)
        # 出典は箇条書きと同じ順に並べる決まり。数が合わないときは結び付けない。
        paired = len(sources) == len(bullets)

        for i, line in enumerate(bullets):
            text, note = split_note(line)
            start, end = parse_dates(text, written)
            items.append({
                "text": text,
                "note": note,
                "kind": guess_kind(text),
                "area": guess_area(text),
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                "source": sources[i] if paired else None,
                "written": written.isoformat(),
            })

    # 同じ本文が二度入っていたら、新しく書いたほうを残す
    seen: set[str] = set()
    unique = []
    for it in sorted(items, key=lambda x: x["written"], reverse=True):
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        unique.append(it)
    return unique


def build(md: str) -> dict:
    items = parse_neta(md)
    for it in items:
        it["region"] = ("嶺南" if it["area"] in REINAN else "嶺北") if it["area"] else None
    # 実行日ではなくネタの最新日にする（中身が同じなら毎日コミットが出ないように）
    updated = max((it["written"] for it in items), default=None)
    return {"updated": updated, "items": items}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="書き出さずに件数だけ表示する")
    args = ap.parse_args(argv)

    data = build(NETA.read_text(encoding="utf-8"))
    items = data["items"]
    counts = {k: sum(1 for i in items if i["kind"] == k) for k in ("催し", "スポット", "話題")}
    undated = sum(1 for i in items if not i["start"])
    print(f"{len(items)} 件（{'・'.join(f'{k}{v}' for k, v in counts.items())}、日付なし {undated}）")

    if not args.check:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
