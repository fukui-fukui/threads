"""楽天トラベルの「【福井】◯◯な宿◯選」を、明日ぶんに1本足す（AI は使わない）

2026-10-12 代表指示（運用部・福井担当経由）：
  「楽天トラベルの投稿、〇〇選も投稿してください。添付のように1行づつにする、
   リンクURLを表示せず、カードで見せる」
参考にした形（代表が共有した別アカウントの投稿）：
  1本目 … 見出しのあと、1軒1行で「①🏨宿名（県・市町）」
  返信  … 1軒に1本。「【PR】／①🏨宿名／📍県・市町／⭐口コミ 4.4（123件）／詳しくはこちら👇」
          リンクは URL の文字にせず、返信のリンクカード（link_attachment）で見せる

- 2026-10-12 代表「催し+宿と〇〇選を1日おきでいいですよ」：15:00 で「催し × 宿」と1日おきに出す
  （どちらの日かは 宿.まとめの日。宿◯選の日は compose が 15:00 を作らない）
- 切り口は scripts/宿.py の切り口（大浴場・露天風呂・サウナ・エリアなど）。日付で回す
- 見出しに出典の無い誇張（「正直教えたくない」など）は使わない
- 評価とレビュー数は宿のリストの数字だけ
- region.json の「使う」で「宿まとめ」が true のときだけ動く（既定は出さない）

環境変数:
  ROUNDUP_HOUR … 何時に出すか（既定 15）
  TARGET_DATE  … 対象日（無ければ明日）
  DRY_RUN      … "true" なら表示だけ
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import 地域  # noqa: E402
import 宿  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
QUEUE = Path("posts/queue.jsonl")
上限 = 500
印 = "宿まとめ"


def 使うか() -> bool:
    return bool(地域.地域.get("使う", {}).get("宿まとめ", False))


def 対象日():
    t = os.environ.get("TARGET_DATE", "").strip()
    if t:
        return datetime.strptime(t, "%Y-%m-%d").date()
    return (datetime.now(JST) + timedelta(days=1)).date()


def 温泉の切り口() -> dict | None:
    return next((き for き in 宿.切り口たち if str(き.get("名", "")).startswith("温泉")), None)


def 絵文字(h: dict) -> str:
    """宿の種類で絵文字を変える。温泉は人工のものを除いた「温泉」の切り口で見る。"""
    種別 = str(h.get("種別") or "")
    if "グランピング" in 種別:
        return "⛺"
    if "一棟貸し" in 種別:
        return "🏡"
    温 = 温泉の切り口()
    if 温 and 宿.当てはまる(温, h):
        return "♨️"
    return "🏨"


def 見出し(まとめ: dict) -> str:
    き = まとめ["切り口"]
    問い = str(き.get("問い") or き.get("名") or "").strip()
    絵 = "♨️" if any(w in 問い for w in ("温泉", "風呂", "サウナ", "浴場")) else "🏨"
    return f"【{宿.県名}】{問い}{len(まとめ['宿'])}選{絵}"


def 場所(h: dict) -> str:
    return f"{宿.県の名(h)}・{宿.市町(h)}"


def 本文(まとめ: dict) -> str:
    行 = [f"{宿.丸数字[i]}{絵文字(h)}{宿.見せる名(h)}（{場所(h)}）" for i, h in enumerate(まとめ["宿"])]
    return 見出し(まとめ) + "\n\n" + "\n".join(行)


def 返信(i: int, h: dict) -> str:
    行 = ["【PR】", f"{宿.丸数字[i]}{絵文字(h)}{宿.見せる名(h)}", f"📍{場所(h)}"]
    評価, 件 = h.get("評価"), h.get("レビュー数")
    if isinstance(評価, (int, float)) and 評価 > 0 and isinstance(件, int) and 件 > 0:
        行.append(f"⭐口コミ {評価:.1f}（{件:,}件）")
    行.append("詳しくはこちら👇")
    return "\n".join(行)


def 直近に出した宿(すでに: list[dict], 日, 宿たち: list[dict], 日数: int = 14) -> set[str]:  # 宿も14日あける（2026-10-28 代表「14日にして」）
    """対象日の前 日数 日の宿まとめ（note が「宿まとめ」）の本文に出ている宿の名前。"""
    始め = (日 - timedelta(days=日数)).isoformat()
    本文たち = [str(e.get("text") or "") for e in すでに
               if str(e.get("note") or "").startswith(印) and 始め <= str(e.get("scheduled_at") or "")[:10] < 日.isoformat()]
    return {宿.見せる名(h) for h in 宿たち if any(宿.見せる名(h) in t for t in 本文たち)}


def 組み立てる(日, 宿たち: list[dict], 時: int, 避ける: set[str] = frozenset()) -> dict | None:
    まとめ = 宿.今日のまとめ(日, 宿たち, いくつ=宿.今日の件数(日, 5, 7), 避ける=避ける)
    if not まとめ:
        return None
    # 1本目が長すぎるときは下から減らす（見出しの数も合わせる）
    while len(本文(まとめ)) > 上限 and len(まとめ["宿"]) > 3:
        まとめ = {**まとめ, "宿": まとめ["宿"][:-1]}
    短縮 = 宿.短縮を読む()
    リンク = [宿.宿のリンク先(h, 短縮) for h in まとめ["宿"]]
    if not all(u.startswith("http") for u in リンク):
        return None
    印字 = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return {
        "id": f"p-{日:%Y%m%d}{時:02d}-{印字}",
        "text": 本文(まとめ),
        "scheduled_at": f"{日.isoformat()}T{時:02d}:00:00+09:00",
        "thread": [返信(i, h) for i, h in enumerate(まとめ["宿"])],
        "thread_links": リンク,
        "note": f"{印}（{len(まとめ['宿'])}選・{まとめ['切り口'].get('名')}）／返信のリンクはカードで見せる"[:120],
    }


def main() -> None:
    if not 使うか():
        print("宿まとめは使わない設定です（region.json の 使う.宿まとめ）。何もしません。")
        return
    if not 地域.使う("宿"):
        print("宿を使わない設定です。何もしません。")
        return
    時 = int(os.environ.get("ROUNDUP_HOUR", "15"))
    日 = 対象日()
    if not 宿.まとめの日(日):
        print(f"{日} は「催し × 宿」の日です。宿◯選は足しません。")
        return
    すでに = [json.loads(l) for l in QUEUE.read_text(encoding="utf-8").splitlines() if l.strip()] if QUEUE.exists() else []
    if any(str(e.get("scheduled_at", "")).startswith(f"{日.isoformat()}T{時:02d}:") for e in すでに):
        print(f"{日} {時}:00 はすでに埋まっています。宿まとめは足しません。")
        return
    宿たち = 宿.読む()
    避ける = 直近に出した宿(すでに, 日, 宿たち) if 宿たち else set()
    投稿 = 組み立てる(日, 宿たち, 時, 避ける) if 宿たち else None
    if not 投稿:
        print(f"::warning::{日} の宿まとめは作れませんでした（5軒そろう切り口が無い・リンクが無いなど）。")
        return
    print(f"=== {時}:00 宿まとめ ({len(投稿['text'])} 字) ===\n{投稿['text']}")
    for t, u in zip(投稿["thread"], 投稿["thread_links"]):
        print(f"--- 返信 ---\n{t}\n[カード] {u}")
    if os.environ.get("DRY_RUN", "").lower() == "true":
        print("DRY_RUN のため、キューには書き込みません。")
        return
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(投稿, ensure_ascii=False) + "\n")
    print(f"キューに {日} {時}:00 の宿まとめを1本足しました。")


if __name__ == "__main__":
    main()
