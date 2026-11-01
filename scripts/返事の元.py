"""ダッシュボードの「コメント対応」（返事の案）に、元の投稿の本文・URL と、コメントの URL を足す材料を作る。

2026-11-01 代表「返事の案ごとに、元の投稿（こちらの投稿の本文と、相手のコメント）も見えるように。投稿へのリンクもあると助かる」。
毎朝の作業で、items の返事の案のうち 元の投稿のURL が無いものを、次の順で埋める。

1. 非公開の置き場の <地域>/返信/元.json（scripts/返信を読む.py が書く。返信の URL もある）
2. 無ければ <地域>/返信/*.md（ファイル名が元の投稿の ID、行に返信の ID）から元の投稿を見つけ、
   その地域のリポジトリの state/posted.json（URL）と posts/queue.jsonl（本文）で埋める（返信の URL は空のまま）

  python scripts/返事の元.py <odekake-data> <items のフォルダ> <出力.json> --fukui … --ishikawa … --gifuaichi … --ekimae …

出力は [{"id": doc の id, "version": 読んだ版, "data": {足す項目}}]。中身（読者の返信の本文）は出力に入れない。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

地域 = {"ふくいおでかけ": ("fukui", "fukui"), "いしかわおでかけ": ("ishikawa", "ishikawa"),
       "ぎふあいちおでかけ": ("gifu-aichi", "gifuaichi"), "ふくいエキマエ": ("ekimae", "ekimae")}
_行 = re.compile(r"ID (\d+)・親 (\d+)\]")


def 元の記録(data: Path, 置き場: str) -> dict[str, dict]:
    p = data / 置き場 / "返信" / "元.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def mdの元(data: Path, 置き場: str) -> dict[str, str]:
    """返信の ID → 元の投稿の ID（返信/<日>_<投稿ID>.md から）"""
    出 = {}
    for f in sorted((data / 置き場 / "返信").glob("*_*.md")):
        元 = f.stem.split("_", 1)[1]
        for m in _行.finditer(f.read_text(encoding="utf-8")):
            出.setdefault(m.group(1), 元)
    return 出


def 自分の投稿(repo: Path | None) -> dict[str, dict]:
    """投稿の ID → {URL, 本文}（state/posted.json と posts/queue.jsonl から）"""
    if not repo:
        return {}
    try:
        posted = json.loads((repo / "state/posted.json").read_text(encoding="utf-8")).get("posted", {})
    except (FileNotFoundError, ValueError):
        return {}
    本文 = {}
    q = repo / "posts/queue.jsonl"
    if q.exists():
        for l in q.read_text(encoding="utf-8").splitlines():
            if l.strip():
                e = json.loads(l)
                本文[e.get("id")] = e.get("text") or ""
    return {str(v.get("post_id")): {"URL": v.get("permalink") or "", "本文": 本文.get(k, "")}
            for k, v in posted.items() if v.get("post_id")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("items", type=Path)
    ap.add_argument("out", type=Path)
    for k in ("fukui", "ishikawa", "gifuaichi", "ekimae"):
        ap.add_argument(f"--{k}", type=Path)
    a = ap.parse_args()
    記録, md, 自分 = {}, {}, {}
    出 = []
    for f in sorted(a.items.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("種類") != "返事の案" or d.get("元の投稿のURL") or not d.get("reply_to"):
            continue
        if d.get("出どころ") not in 地域:
            continue
        置き場, 引数 = 地域[d["出どころ"]]
        if 置き場 not in 記録:
            記録[置き場] = 元の記録(a.data, 置き場)
            md[置き場] = mdの元(a.data, 置き場)
            自分[置き場] = 自分の投稿(getattr(a, 引数))
        r = str(d["reply_to"])
        足す = dict(記録[置き場].get(r) or {})
        if not 足す.get("元の投稿のURL"):
            元 = 足す.get("元の投稿ID") or md[置き場].get(r)
            if 元 and 元 in 自分[置き場]:
                足す.update({"元の投稿ID": 元, "元の投稿のURL": 自分[置き場][元]["URL"],
                           "元の投稿の本文": 足す.get("元の投稿の本文") or 自分[置き場][元]["本文"]})
        足す = {k: v for k, v in 足す.items() if v}
        if 足す.get("元の投稿のURL") or 足す.get("返信のURL"):
            出.append({"id": f.stem, "data": 足す})
    a.out.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"返事の案に元の投稿を足せるもの：{len(出)} 件")


if __name__ == "__main__":
    main()
