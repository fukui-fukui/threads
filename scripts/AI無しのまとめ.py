"""作成（AI）が使えない日に、06時の「今日で終わる催し」と金曜の「今週末のまとめ」を AI を使わずに組む。

2026-11-23 統括（代表「B：上げずに12/1まで作成を止める」）：費用0で、運用部の手入れを減らす。福井・石川・ぎふあいち共通。
材料はネタ帳から作るサイトのデータ（scripts/おでかけ.py の build。会期・市町・出典がそろったもの）だけ。
書くのは、催しの名前・市町・会期と出典の URL だけ（出典にある事実だけ）。
  - 出典は公式だけ。URL が無いもの、催しの一覧サイト（walkerplus など）だけのものは使わない
  - 06時：今日が最終日の催し（2日以上つづいたもの）を、市町がばらけるように3〜5件。3件に満たなければ作らない
  - 金曜の今週末まとめ（region.json の 使う.今週末まとめ の県だけ。時刻は WEEKEND_HOUR）：土日に行ける催しを3〜5件
  - その時刻がもう埋まっていれば何もしない（作成・手入れ・予備を上書きしない）

  python scripts/AI無しのまとめ.py          （TARGET_DATE・DRY_RUN は compose.py と同じ）
"""
from __future__ import annotations

import json
import os
import random
import re
import string
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import おでかけ as サイト  # noqa: E402
import 地域  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "posts" / "queue.jsonl"
上限 = 500
丸数字 = "①②③④⑤"
WD = "月火水木金土日"
一覧サイト = ("walkerplus.com", "jorudan.co.jp", "iko-yo.net", "enjoytokyo", "jalan.net", "tripadvisor", "asoview.com")
朝の時 = 6
WEEKEND_HOUR = 19


def 出典(it: dict) -> str | None:
    """公式の出典の URL（無ければ None）。"""
    urls = [it["source"]] if it.get("source") else []
    urls += re.findall(r"https?://[^\s）)」、。]+", it.get("text") or "")
    for u in urls:
        if not any(d in u for d in 一覧サイト):
            return u
    return None


def 名前(it: dict) -> str:
    return サイト._title(it).strip()[:40]


def 市町がばらける(候補: list[dict], いくつ: int) -> list[dict]:
    選ぶ, 見た = [], set()
    for it in 候補:
        if it.get("area") in 見た:
            continue
        選ぶ.append(it)
        見た.add(it.get("area"))
        if len(選ぶ) == いくつ:
            return 選ぶ
    for it in 候補:
        if len(選ぶ) == いくつ:
            break
        if it not in 選ぶ:
            選ぶ.append(it)
    return 選ぶ


def 使える催し(items: list[dict]) -> list[dict]:
    出 = []
    for it in items:
        if it.get("kind") != "催し" or not サイト._span(it) or not 出典(it) or not 名前(it):
            continue
        出.append(it)
    # 同じ名前は1つだけ
    見た, 重ならない = set(), []
    for it in 出:
        if 名前(it) not in 見た:
            見た.add(名前(it))
            重ならない.append(it)
    return 重ならない


def _短い日(d: date) -> str:
    return f"{d.month}/{d.day}"


def 今日で終わる(items: list[dict], 日: date) -> dict | None:
    候補 = [it for it in 使える催し(items) if サイト._span(it)[1] == 日 and サイト._span(it)[0] < 日]
    候補.sort(key=lambda it: (サイト._span(it)[0], 名前(it)))
    選ぶ = 市町がばらける(候補, 5)
    if len(選ぶ) < 3:
        print(f"{日} が最終日の催しは {len(選ぶ)} 件で、3件に届かないので作りません。")
        return None
    頭 = 地域.地域.get("見出しの頭") or f"【{地域.県名}】"
    本文 = f"{頭}今日で終わる催し{len(選ぶ)}つ\n\n" + "\n".join(
        f"{丸数字[i]} {名前(it)}（{it.get('area') or 地域.県名}）" for i, it in enumerate(選ぶ))
    返信 = [f"{it.get('area') or 地域.県名}｜{名前(it)}（{_短い日(サイト._span(it)[0])}〜{_短い日(日)}）\n"
            f"今日までです。\n出典元：{出典(it)}" for it in 選ぶ]
    return {"本文": 本文, "返信": 返信, "note": f"AI無しのまとめ／今日で終わる催し（{len(選ぶ)}件）"}


def 今週末(items: list[dict], 日: date) -> dict | None:
    土, 日曜 = 日 + timedelta(days=1), 日 + timedelta(days=2)
    候補 = [it for it in 使える催し(items) if サイト._on(it, 土) or サイト._on(it, 日曜)]
    # 短い催し（その週末だけのもの）を先に。長い展示は後ろ
    候補.sort(key=lambda it: (サイト._is_long(サイト._span(it)), サイト._span(it)[0], 名前(it)))
    選ぶ = 市町がばらける(候補, 5)
    if len(選ぶ) < 3:
        print(f"{土}・{日曜} の催しは {len(選ぶ)} 件で、3件に届かないので作りません。")
        return None

    def いつ(it):
        a, b = サイト._on(it, 土), サイト._on(it, 日曜)
        return "土日" if a and b else ("土" if a else "日")

    頭 = 地域.地域.get("見出しの頭") or f"【{地域.県名}】"
    本文 = (f"{頭}今週末（{土.month}/{土.day}・{日曜.day}）のイベント{len(選ぶ)}選\n\n"
            + "\n".join(f"{丸数字[i]} {名前(it)}（{it.get('area') or 地域.県名}・{いつ(it)}）" for i, it in enumerate(選ぶ)))
    返信 = []
    for it in 選ぶ:
        s, e = サイト._span(it)
        会期 = _短い日(s) if s == e else f"{_短い日(s)}〜{_短い日(e)}"
        返信.append(f"{it.get('area') or 地域.県名}｜{名前(it)}（{会期}）\n出典元：{出典(it)}")
    return {"本文": 本文, "返信": 返信, "note": f"AI無しのまとめ／今週末のイベント（{len(選ぶ)}件）"}


def 対象日() -> date:
    t = os.environ.get("TARGET_DATE", "").strip()
    if t:
        return datetime.strptime(t, "%Y-%m-%d").date()
    return (datetime.now(JST) + timedelta(days=1)).date()


def _埋まっている(行たち: list[dict], 日: date, 時: int) -> bool:
    return any(str(e.get("scheduled_at", "")).startswith(f"{日.isoformat()}T{時:02d}:00") for e in 行たち)


def main() -> None:
    日 = 対象日()
    行たち = []
    if QUEUE.exists():
        for l in QUEUE.read_text(encoding="utf-8").splitlines():
            if l.strip() and not l.startswith("#"):
                try:
                    行たち.append(json.loads(l))
                except json.JSONDecodeError:
                    pass
    items = サイト.build((ROOT / "neta" / "ネタ帳.md").read_text(encoding="utf-8"))["items"]
    作る = [(朝の時, 今日で終わる)]
    if 地域.地域.get("使う", {}).get("今週末まとめ") and 日.weekday() == 4:
        作る.append((int(地域.地域.get("WEEKEND_HOUR", WEEKEND_HOUR)), 今週末))
    足す = []
    for 時, 組む in 作る:
        if _埋まっている(行たち + 足す, 日, 時):
            print(f"{日} {時}:00 はすでに埋まっています。")
            continue
        x = 組む(items, 日)
        if not x:
            continue
        if len(x["本文"]) > 上限 or any(len(t) > 上限 for t in x["返信"]):
            print(f"::warning::{日} {時}:00 は長すぎるので作りません。")
            continue
        印字 = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        足す.append({"id": f"p-{日:%Y%m%d}{時:02d}-{印字}", "text": x["本文"],
                    "scheduled_at": f"{日.isoformat()}T{時:02d}:00:00+09:00", "thread": x["返信"], "note": x["note"]})
        print(f"=== {時}:00 ===\n{x['本文']}")
        for t in x["返信"]:
            print(f"--- 返信 ---\n{t}")
    if os.environ.get("DRY_RUN", "").lower() == "true":
        print("DRY_RUN のため、キューには書き込みません。")
        return
    if 足す:
        with QUEUE.open("a", encoding="utf-8") as f:
            for e in 足す:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"AI無しのまとめを {len(足す)} 本足しました。")


if __name__ == "__main__":
    main()
