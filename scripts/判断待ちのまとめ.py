"""ダッシュボードの「判断待ち」で、同じ内容の候補を1件にまとめる。

2026-11-01 代表「判断待ちに入っているもので同じ内容のものはまとめてください」。
同じ催し・同じお店が、作成で外した・情報集めで外した、と毎日のように別の札で入り、同じものが何件も並んでいた。

まとめ方：
- まだ答えていない（答え が空・取り込み済み でない）判断待ちの候補どうしで、同じ URL（url の欄か中身の中の URL）か、
  同じ「」の名前（4字以上）があれば同じ内容とみる。
- いちばん新しく入った1件を残し、ほかの札には まとめ先（残した札の id）を付ける。ダッシュボードは まとめ先 のある札を出さない。
- 残した札には ほかの理由（まとめた札の 中身 と 入った日）を足す。新しい出典はここに残る。
- 似ているが別の催し（同じ会場の別の催しなど）は、URL も「」の名前も違うのでまとまらない。迷うものは人が見て決める。

  python scripts/判断待ちのまとめ.py <items のフォルダ> <出力.json> [--new <今朝の新しい候補.json>]

--new を付けると、まだ set していない今朝の候補も含めて見る（新しい候補は、既にある札にまとめられるなら まとめ先 を付けて set する）。
出力は {"set": [新しい候補（まとめ先つき）], "update": [{"id", "data"}]}。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_URL = re.compile(r"https?://[^\s<>\"'「」『』（）()、。，,]+")
_名 = re.compile(r"「([^「」]{4,40})」")
判断待ちでない = ("返事の案", "掲載の申し込み", "問い合わせ")


def URLたち(d: dict) -> set[str]:
    文 = f"{d.get('url') or ''} {d.get('中身') or ''}"
    出 = set()
    for u in _URL.findall(文):
        u = u.rstrip(".:;!?").split("#")[0].rstrip("/")
        # 一覧のページ（トップ・イベント一覧）は別の催しでも同じなので、手がかりにしない
        if re.search(r"://[^/]+/?$|/(index[^/]*\.html?|calendar\.php|event/?|events/?)$", u):
            continue
        出.add(u)
    return 出


def 名前たち(d: dict) -> set[str]:
    return set(_名.findall(str(d.get("中身") or "")))


def 鍵(d: dict) -> set[str]:
    return {f"u:{u}" for u in URLたち(d)} | {f"n:{n}" for n in 名前たち(d)}


def 開いている(d: dict) -> bool:
    return (d.get("種類") not in 判断待ちでない and not str(d.get("id", "")).startswith(("rep-", "sub-", "inq-"))
            and not d.get("答え") and not d.get("取り込み済み") and not d.get("まとめ先"))


def まとめる(既存: list[dict], 新: list[dict]) -> dict:
    札 = [d for d in 既存 if 開いている(d)] + [{**d, "_新": True} for d in 新]
    # 鍵を共有する札を1つの組にする（union-find）
    親 = list(range(len(札)))

    def 根(i):
        while 親[i] != i:
            親[i] = 親[親[i]]
            i = 親[i]
        return i
    持ち主: dict[str, int] = {}
    for i, d in enumerate(札):
        for k in 鍵(d):
            if k in 持ち主:
                親[根(i)] = 根(持ち主[k])
            else:
                持ち主[k] = i
    組: dict[int, list[int]] = {}
    for i in range(len(札)):
        組.setdefault(根(i), []).append(i)
    set_, update = [], []
    for 番号 in 組.values():
        if len(番号) < 2:
            continue
        # 既にある札を優先して残す（新しい候補は既存にまとめる）。インスタの札は「引用」を選べるので、同じ並びならインスタを残す。
        # その中でいちばん新しく入ったもの
        並び = sorted(番号, key=lambda i: (not 札[i].get("_新"), str(札[i].get("種類") or "").startswith("インスタ"),
                                          str(札[i].get("入った日") or ""), str(札[i].get("日") or "")))
        残す = 札[並び[-1]]
        ほか = [札[i] for i in 並び[:-1]]
        理由 = list(残す.get("ほかの理由") or [])
        for d in ほか:
            理由.append({"中身": d.get("中身") or "", "入った日": d.get("入った日") or d.get("日") or "", "url": d.get("url") or ""})
            if d.get("_新"):
                set_.append({k: v for k, v in d.items() if k != "_新"} | {"まとめ先": 残す["id"]})
            else:
                update.append({"id": d["id"], "data": {"まとめ先": 残す["id"]}})
        if 残す.get("_新"):
            # 残す札も今朝の新しい候補なら、まだ doc が無いので set の中身に入れる
            set_.append({k: v for k, v in 残す.items() if k != "_新"} | {"ほかの理由": 理由})
        else:
            update.append({"id": 残す["id"], "data": {"ほかの理由": 理由}})
    # まとめられなかった新しい候補はそのまま set する
    まとめた = {d["id"] for d in set_}  # まとめ先を付けた候補と、ほかの理由を足した新しい候補
    set_ += [d for d in 新 if d["id"] not in まとめた]
    return {"set": set_, "update": update}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("items", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--new", type=Path)
    a = ap.parse_args()
    既存 = [{**json.loads(f.read_text(encoding="utf-8")), "id": f.stem} for f in sorted(a.items.glob("*.json"))]
    新 = json.loads(a.new.read_text(encoding="utf-8")) if a.new else []
    r = まとめる(既存, 新)
    a.out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    残す = [(u["id"], u["data"]["ほかの理由"]) for u in r["update"] if "ほかの理由" in u["data"]]
    残す += [(d["id"], d["ほかの理由"]) for d in r["set"] if d.get("ほかの理由") and not d.get("まとめ先")]
    既存 = sum(1 for u in r["update"] if "まとめ先" in u["data"])
    print(f"まとめた組：{len(残す)}・まとめ先を付けた札：{既存}（既存）＋{sum(1 for d in r['set'] if d.get('まとめ先'))}（新しい候補）")
    for i, 理由 in 残す:
        print(f"  残す {i} ← {len(理由)} 件")


if __name__ == "__main__":
    main()
