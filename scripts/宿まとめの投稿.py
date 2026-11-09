"""楽天トラベルの「【福井】◯◯な宿◯選」を、明日ぶんに1本足す（AI は使わない）

2026-10-12 代表指示（運用部・福井担当経由）：
  「楽天トラベルの投稿、〇〇選も投稿してください。添付のように1行づつにする、
   リンクURLを表示せず、カードで見せる」
参考にした形（代表が共有した別アカウントの投稿）：
  1本目 … 見出しのあと、1軒1行で「①🏨宿名（県・市町）」
  返信  … 1軒に1本。「①🏨宿名／📍県・市町／⭐口コミ 4.4（123件）／詳しくはこちら👇／PR」（PR は最後。2026-11-09 代表）
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
import re
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
    # yu と同じく、見出しの終わりに絵文字は付けない（2026-11-02 代表「yu の◯選の出し方を、そのままおでかけの◯選に」）
    return f"【{宿.県名}】{問い}{len(まとめ['宿'])}選"


def 場所(h: dict) -> str:
    return f"{宿.県の名(h)}・{宿.市町(h)}"


def 本文(まとめ: dict) -> str:
    # yu の◯選と同じ形：見出しと「① 🌊 宿名（市町）」の行だけ（2026-11-02 代表「yu の◯選の出し方を、そのままおでかけの◯選に」。
    # 同じ切り口で yu は閲覧 1,600〜1,800、福井は 60〜100 だった）
    # 本文の最後に PR（2026-11-03 代表「本文の最後にPR」。冒頭の【PR】は 9/25 の決定どおり避ける）
    return 見出し(まとめ) + "\n\n" + "\n".join(宿.一覧の行(まとめ)) + "\n\nPR"


def まとめの返信(まとめ: dict) -> list[str]:
    """返信。宿ごとに「① 宿名（市町。楽天の紹介文から一言）」とリンクを並べ、最後に PR（yu と同じ）。
    ふつうは1本。リンクが長くて 500 字を超えるときだけ、yu と同じく続きの返信に分ける（どの返信も末尾に PR）。"""
    出, いま = [], "楽天トラベルのページはこちらです"
    for 行 in 宿.返信の行(まとめ):
        つぎ = いま + "\n\n" + 行
        if len(つぎ + "\n\nPR") > 上限 and いま != "楽天トラベルのページはこちらです":
            出.append(いま)
            いま = 行
        else:
            いま = つぎ
    出.append(いま)
    return [x + "\n\nPR" for x in 出]


def 返信(i: int, h: dict) -> str:
    # PR は最後の1行に（2026-11-09 代表「PRを先頭につけない。投稿文の最後につける。全てに共通の仕様で」）
    行 = [f"{宿.丸数字[i]}{絵文字(h)}{宿.見せる名(h)}", f"📍{場所(h)}"]
    評価, 件 = h.get("評価"), h.get("レビュー数")
    if isinstance(評価, (int, float)) and 評価 > 0 and isinstance(件, int) and 件 > 0:
        行.append(f"⭐口コミ {評価:.1f}（{件:,}件）")
    行.append("詳しくはこちら👇")
    return "\n".join(行 + ["", "PR"])


def 直近に出した宿(すでに: list[dict], 日, 宿たち: list[dict], 日数: int = 14) -> set[str]:  # 宿も14日あける（2026-10-28 代表「14日にして」）
    """対象日の前後 日数 日の投稿（宿◯選・催し × 宿・宿1軒のどれでも。本文と返信）に出ている宿の名前。"""
    始め, 終わり = (日 - timedelta(days=日数)).isoformat(), (日 + timedelta(days=日数)).isoformat()
    本文たち = ["\n".join([str(e.get("text") or ""), *[str(t) for t in (e.get("thread") or [])]]) for e in すでに
               if 始め <= str(e.get("scheduled_at") or "")[:10] <= 終わり]
    return {宿.見せる名(h) for h in 宿たち if any(宿.見せる名(h) in t for t in 本文たち)}


# ---------------------------------------------------------------
# 宿1軒の紹介（2026-11-01 代表「まとめて数件の投稿だけでなく、1件をしっかりと紹介する投稿もするように」）
# 参考：代表が共有した別アカウント（ひとり旅の宿）。本文で「誰に・一番の売り・料金」、返信に｜区切りの事実とリンク。
# 書くのは宿のリスト（楽天トラベルの API で取った事実）だけ。AI は使わない。
# 楽天の「最安」は1名1泊の料金とはかぎらないので、「1名◯円」とは書かず「最安◯円〜（◯/◯時点）」にする。
# ---------------------------------------------------------------
一軒の切り口の種類 = (None, "チェックアウト", "最終チェックイン", "朝食バイキング", "駐車場無料")


def 一軒を選ぶ(日, 宿たち: list[dict], 避ける: set[str] = frozenset()) -> tuple[dict, dict, str] | None:
    """その日の切り口と、当てはまる宿1軒と、当てはまった事実。日付から決める。"""
    切り口 = [き for き in 宿.切り口たち if き.get("種類") in 一軒の切り口の種類]
    n = (日 - 宿.起点).days
    for i in range(len(切り口)):
        き = 切り口[(n + i) % len(切り口)]
        合う = [h for h in sorted(宿たち, key=lambda x: str(x.get("番号")))
              if 宿.見せる名(h) not in 避ける and isinstance(h.get("最安"), int) and h["最安"] > 0 and 宿.当てはまる(き, h)]
        if 合う:
            h = 合う[n % len(合う)]
            return き, h, 宿.当てはまる(き, h)
    return None


def _時点(h: dict) -> str:
    d = str(h.get("調べた日") or "")
    try:
        x = datetime.strptime(d, "%Y-%m-%d")
        return f"{x.month}/{x.day}時点"
    except ValueError:
        return "調べた日の時点"


def _口コミ(h: dict) -> str:
    評価, 件 = h.get("評価"), h.get("レビュー数")
    if isinstance(評価, (int, float)) and 評価 > 0 and isinstance(件, int) and 件 > 0:
        return f"{評価:.1f}（{件:,}件）"
    return ""


def 一軒の本文(き: dict, h: dict, 事実: str, リンク: str = "") -> str:
    名 = 宿.見せる名(h)
    問い = str(き.get("問い") or "").strip()
    行 = [f"{宿.市町(h)}で、{問い}を探している人へ。", ""]
    種類 = き.get("種類")
    if 種類 is None:
        # 設備の切り口の事実は宿の紹介文そのまま（「■大浴場は東館8階に…」のように長い・記号入り）のことがあるので、
        # 本文では切り口の言葉で言う（おでかけ開発のレビュー）
        行.append(f"「{名}」は、{問い}です。")
    elif 種類 == "チェックアウト":
        行.append(f"「{名}」は、チェックアウトが {h.get('チェックアウト')}。")
    elif 種類 == "最終チェックイン":
        行.append(f"「{名}」は、最終チェックインが {h.get('最終チェックイン')}。")
    elif 種類 == "朝食バイキング":
        行.append(f"「{名}」の朝食は、{事実}。")
    else:
        行.append(f"「{名}」の駐車場は、{事実}。")
    if _口コミ(h):
        行.append(f"楽天トラベルの口コミは {_口コミ(h)}。")
    行 += ["", f"楽天トラベルの最安料金は {h['最安']:,}円〜（{_時点(h)}）。"]
    # 1商品（宿）の紹介は、1投稿目にリンクを付け、本文の最後に PR（2026-11-03 代表「本文の最後にPR。また、1商品（宿）紹介の場合は1投稿目にリンクを付ける」）
    if リンク:
        行 += ["", "空室と今の料金はこちら👇", リンク]
    行 += ["", "PR"]
    return "\n".join(行)


def _お風呂(h: dict) -> str:
    風呂 = [str(x).strip() for x in (h.get("風呂") or []) if str(x).strip()]
    if 風呂:
        return "、".join(dict.fromkeys(x[:20] for x in 風呂[:2]))
    設備 = [str(x) for x in (h.get("館内設備") or [])]
    return "、".join(w for w in ("大浴場", "露天風呂", "サウナ") if any(w in x for x in 設備))


def _朝食(h: dict) -> str:
    """朝食の場所。「レストラン」と「レストラン(バイキング)」のように重なるときは、くわしいほうだけ残す（2026-11-01 統括）。"""
    場所 = list(dict.fromkeys(str(x).strip().replace("(", "（").replace(")", "）") for x in (h.get("朝食の場所") or []) if str(x).strip()))
    return "・".join(x for x in 場所 if not any(y != x and y.startswith(x) for y in 場所))


def _駐車場(h: dict, 上限: int = 40) -> str:
    """駐車場の説明を、文の途中で切らずに短くする（2026-11-01 統括「途中で切らず、切るなら文の区切りで」）。
    宿の登録のまま（データにある事実だけ）で、※・。の区切りごとに、上限の字数までを残す。"""
    文 = " ".join(str(h.get("駐車場") or "").replace("\\", "¥").split())
    if len(文) <= 上限:
        return 文
    出 = ""
    for 区切り in re.split(r"(?<=。)|(?=※)", 文):
        区切り = 区切り.strip()
        if not 区切り:
            continue
        if 出 and len(出) + 1 + len(区切り) > 上限:
            break
        出 = f"{出} {区切り}".strip() if 出 else 区切り
        if len(出) > 上限:
            break
    # 最初の区切りだけで長いときは、読点・スラッシュ・空白の区切りまで
    if len(出) > 上限:
        部分 = re.split(r"(?<=[、/／])|\s+", 出)
        出 = ""
        for x in 部分:
            if 出 and len(出) + len(x) > 上限:
                break
            出 += x
    return 出.strip(" 、/／")


def 一軒の返信(h: dict) -> str:
    # PR は最後の1行に（2026-11-09 代表「PRを先頭につけない。投稿文の最後につける」）
    行 = [f"{絵文字(h)}{宿.見せる名(h)}｜{場所(h)}", f"｜最安 {h['最安']:,}円〜（{_時点(h)}）"]
    if _お風呂(h):
        行.append(f"｜お風呂：{_お風呂(h)}")
    朝食 = _朝食(h)
    if 朝食:
        行.append(f"｜朝食：{朝食}")
    if h.get("最寄駅"):
        行.append(f"｜最寄り駅：{h['最寄駅']}")
    駐車 = _駐車場(h)
    if 駐車:
        行.append(f"｜駐車場：{駐車}")
    if _口コミ(h):
        行.append(f"｜口コミ：⭐{_口コミ(h)}")
    行 += ["", "※料金・プラン内容は宿泊日によって変動します", "", "PR"]
    return "\n".join(行)


def 最安を取り直す(h: dict) -> dict:
    """宿の最安料金を、楽天トラベルの API（SimpleHotelSearch・無料）で取り直す。取れたら調べた日を今日にする。
    宿のリストは週1回しか作らないので、出す日には1週間前の料金になってしまう（2026-11-01 統括）。
    鍵が無いとき・取れないときは、リストの料金と調べた日のまま。鍵とURLはログに出さない。"""
    アプリ, 鍵 = os.environ.get("RAKUTEN_APP_ID", "").strip(), os.environ.get("RAKUTEN_ACCESS_KEY", "").strip()
    if not アプリ or not 鍵 or not h.get("番号"):
        return h
    import urllib.parse
    import urllib.request
    q = urllib.parse.urlencode({"applicationId": アプリ, "accessKey": 鍵, "format": "json", "hotelNo": h["番号"]})
    ヘッダ = {"accept": "application/json"}
    元 = os.environ.get("RAKUTEN_REFERER", "").strip()
    if 元:
        # 宿を集める.mjs と同じく origin も付ける（referer だけだと HTTPError で取り直せなかった。2026-11-04 ぎふあいち）
        ヘッダ["referer"] = 元
        ヘッダ["origin"] = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(元))
    try:
        req = urllib.request.Request(f"https://openapi.rakuten.co.jp/engine/api/Travel/SimpleHotelSearch/20260731?{q}", headers=ヘッダ)
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
        束 = d["hotels"][0]["hotel"]
        基本 = next(x["hotelBasicInfo"] for x in 束 if "hotelBasicInfo" in x)
        最安 = 基本.get("hotelMinCharge")
        if isinstance(最安, int) and 最安 > 0:
            print(f"最安料金を取り直しました：{h['最安']:,}円 → {最安:,}円")
            return {**h, "最安": 最安, "調べた日": datetime.now(JST).date().isoformat()}
    except Exception as e:  # noqa: BLE001 取れなくてもリストの料金で出す
        # 鍵とURLは出さない。HTTP の番号だけ出す（原因を見るため）
        番号 = getattr(e, "code", "")
        print(f"::warning::最安料金を取り直せませんでした（{type(e).__name__} {番号}）。リストの料金のまま出します")
    return h


def 一軒を組み立てる(日, 宿たち: list[dict], 時: int, 避ける: set[str] = frozenset()) -> dict | None:
    選んだ = 一軒を選ぶ(日, 宿たち, 避ける)
    if not 選んだ:
        return None
    き, h, 事実 = 選んだ
    h = 最安を取り直す(h)
    リンク = 宿.宿のリンク先(h, 宿.短縮を読む())
    if not リンク.startswith("http"):
        return None
    印字 = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return {
        "id": f"p-{日:%Y%m%d}{時:02d}-{印字}",
        "text": 一軒の本文(き, h, 事実, リンク),
        "scheduled_at": f"{日.isoformat()}T{時:02d}:00:00+09:00",
        "thread": [一軒の返信(h)],
        "note": f"{印}（1軒・{き.get('名')}）／{宿.見せる名(h)}／リンクは本文に"[:120],
    }


def 組み立てる(日, 宿たち: list[dict], 時: int, 避ける: set[str] = frozenset()) -> dict | None:
    まとめ = 宿.今日のまとめ(日, 宿たち, いくつ=宿.今日の件数(日), 避ける=避ける)  # yu と同じ 3〜5軒
    if not まとめ:
        return None
    # 本文か返信が長すぎるときは下から減らす（見出しの数も合わせる）
    while (len(本文(まとめ)) > 上限 or len(まとめの返信(まとめ)) > 1) and len(まとめ["宿"]) > 3:
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
        "thread": まとめの返信(まとめ),
        "note": f"{印}（{len(まとめ['宿'])}選・{まとめ['切り口'].get('名')}）／yu と同じ形（返信1本にリンクを並べる）"[:120],
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
    型 = 宿.十五時の型(日)
    if 型 == "催し":
        print(f"{日} は「催し × 宿」の日です。宿◯選・宿1軒は足しません。")
        return
    すでに = [json.loads(l) for l in QUEUE.read_text(encoding="utf-8").splitlines() if l.strip()] if QUEUE.exists() else []
    if any(str(e.get("scheduled_at", "")).startswith(f"{日.isoformat()}T{時:02d}:") for e in すでに):
        print(f"{日} {時}:00 はすでに埋まっています。宿まとめは足しません。")
        return
    宿たち = 宿.読む()
    避ける = 直近に出した宿(すでに, 日, 宿たち) if 宿たち else set()
    if 型 == "一軒":
        投稿 = 一軒を組み立てる(日, 宿たち, 時, 避ける) if 宿たち else None
    else:
        投稿 = 組み立てる(日, 宿たち, 時, 避ける) if 宿たち else None
    if not 投稿:
        print(f"::warning::{日} の宿の投稿（{型}）は作れませんでした（当てはまる宿が無い・リンクが無いなど）。")
        return
    print(f"=== {時}:00 宿の投稿（{型}） ({len(投稿['text'])} 字) ===\n{投稿['text']}")
    リンク = 投稿.get("thread_links") or []
    for i, t in enumerate(投稿["thread"]):
        print(f"--- 返信 ---\n{t}" + (f"\n[カード] {リンク[i]}" if i < len(リンク) else ""))
    if os.environ.get("DRY_RUN", "").lower() == "true":
        print("DRY_RUN のため、キューには書き込みません。")
        return
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(投稿, ensure_ascii=False) + "\n")
    print(f"キューに {日} {時}:00 の宿まとめを1本足しました。")


if __name__ == "__main__":
    main()
