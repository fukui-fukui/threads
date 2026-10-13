"""代表の「判断待ち」ダッシュボードの中身を作る／代表の答えをネタ帳に戻す

2026-10-13 代表（統括経由）：「収集結果を毎日ダッシュボードで更新するやり方はどうですか？私が確認して、回答します。
Metaで収集と、おでかけ2つの収集で、判断に迷ったものを表示。」

  集める … 福井・石川のリポジトリから、判断に迷ったものを JSON で出す
    1. Meta（Instagram）で読んだ新しい投稿のうち、ネタ帳に入らなかったもの（state/インスタ新着.json）
    2. 情報集め・翌日ぶんの作成で、確かめられず外したもの（neta/外した候補.md）
  反映 … 代表の答え（JSON）をリポジトリに戻す
    載せる → ネタ帳の「調べてほしいもの」に足す（翌朝の情報集めが公式で確かめ直して入れる）
    載せない → neta/載せないもの.jsonl に残す（情報集めがその URL を二度と候補にしない）
    保留 → 何もしない
    返事の案（2026-10-13 代表「進めてOK」）：運用部がダッシュボードに置いた、読者の返信への返事の案
      出す → posts/queue.jsonl に reply_to つきで入れる（返事の文と宛先の ID だけ。読者の返信の本文・ユーザー名は書かない）
      出さない・保留 → 何もしない

使い方:
  python scripts/判断待ち.py 集める --fukui . --ishikawa ../odekake-ishikawa > items.json
  python scripts/判断待ち.py 反映 answers.json --fukui . --ishikawa ../odekake-ishikawa
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
見る日数 = 14
出どころの名 = {"fukui": "ふくいおでかけ", "ishikawa": "いしかわおでかけ", "ekimae": "ふくいエキマエ"}


def 印(*部分: str) -> str:
    return hashlib.sha1("␟".join(部分).encode()).hexdigest()[:16]


def _行を分ける(行: str) -> tuple[str, str, str]:
    """「中身（理由） URL」を (中身, 理由, url) に分ける。"""
    s = 行.strip()
    url = ""
    m = re.search(r"\s(https?://\S+)\s*$", s)
    if m:
        url = m.group(1)
        s = s[: m.start()].rstrip()
    理由 = ""
    if s.endswith("）"):
        # 末尾の （…） を、入れ子も見ながら取り出す
        深さ = 0
        for i in range(len(s) - 1, -1, -1):
            if s[i] == "）":
                深さ += 1
            elif s[i] == "（":
                深さ -= 1
                if 深さ == 0:
                    理由 = s[i + 1 : -1]
                    s = s[:i].rstrip()
                    break
    return s, 理由, url


def 外した候補を読む(repo: Path, 出どころ: str, 境目: date) -> list[dict]:
    p = repo / "neta" / "外した候補.md"
    if not p.exists():
        return []
    出, 見出し, 日 = [], "", None
    for 行 in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (\d{4}-\d{2}-\d{2}) (.+)$", 行)
        if m:
            日 = date.fromisoformat(m.group(1))
            見出し = m.group(2)
            continue
        if not 行.startswith("- ") or 日 is None or 日 < 境目:
            continue
        中身, 理由, url = _行を分ける(行[2:])
        if not 中身 or "必須条件" in 中身:
            continue
        種類 = "翌日ぶんの作成で外した" if "作成" in 見出し else "情報集めで外した"
        出.append({"id": 印(出どころ, 中身, url), "出どころ": 出どころ, "種類": 種類, "日": 日.isoformat(),
                   "中身": 中身, "理由": 理由, "url": url})
    return 出


def インスタを読む(repo: Path, 出どころ: str, 境目: date) -> list[dict]:
    """インスタの新しい投稿のうち、そのアカウントがネタ帳のその日の塊に出てこないもの。"""
    p = repo / "state" / "インスタ新着.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    集めた日 = str(d.get("集めた日") or "")
    if not 集めた日 or date.fromisoformat(集めた日) < 境目:
        return []
    ネタ帳 = (repo / "neta" / "ネタ帳.md").read_text(encoding="utf-8")
    m = re.search(rf"^### {集めた日}\n(.*?)(?=^### |\Z)", ネタ帳, re.M | re.S)
    塊 = m.group(1) if m else ""
    出 = []
    for x in d.get("投稿") or []:
        人 = str(x.get("アカウント") or "").replace("Instagram ", "").lstrip("@")
        if 人 and f"instagram.com/{人}" in 塊:
            continue
        url = str(x.get("url") or "")
        中身 = re.sub(r"\s+", " ", str(x.get("本文") or "")).strip()
        # 本文の頭にアカウントの紹介文が付いていることがあるので、アカウント名より後ろを使う
        if 人 and 人 in 中身[:120]:
            中身 = 中身[中身.index(人) + len(人):].strip()
        中身 = 中身[:160]
        出.append({"id": 印(出どころ, "insta", url), "出どころ": 出どころ, "種類": "インスタ（Meta）で読んだ新しい投稿",
                   "日": str(x.get("日付") or 集めた日), "中身": 中身, "理由": f"{x.get('アカウント', '')}の投稿。ネタ帳に入らなかった",
                   "url": url})
    return 出


def 集める(repos: dict[str, Path]) -> list[dict]:
    境目 = datetime.now(JST).date() - timedelta(days=見る日数)
    出 = []
    for 名, repo in repos.items():
        if not repo or not repo.exists() or 名 == "ekimae":
            continue
        出 += インスタを読む(repo, 出どころの名[名], 境目)
        出 += 外した候補を読む(repo, 出どころの名[名], 境目)
    見た, 重ならない = set(), []
    for x in 出:
        if x["id"] not in 見た:
            見た.add(x["id"])
            重ならない.append(x)
    return 重ならない


def _調べもの節に足す(ネタ帳: str, 行たち: list[str]) -> str:
    i = ネタ帳.find("## 調べてほしいもの")
    j = ネタ帳.find("\n## ", i + 1)
    if i < 0 or j < 0:
        raise SystemExit("ネタ帳に「## 調べてほしいもの」の節がありません")
    節 = ネタ帳[i:j].rstrip("\n")
    足す = [l for l in 行たち if l not in 節]
    if not 足す:
        return ネタ帳
    return ネタ帳[:i] + 節 + "\n" + "\n".join(足す) + "\n" + ネタ帳[j:]


def 返事の時刻(今: datetime, 何本目: int) -> str:
    """返事は ◯:00 の枠を埋めないよう、毎時 20〜50 分に10分おきで入れる（compose の枠の数え方は ◯:00 だけ）。"""
    t = (今 + timedelta(minutes=15)).replace(second=0, microsecond=0)
    分 = [20, 30, 40, 50]
    if t.minute > 分[-1]:
        t = (t + timedelta(hours=1)).replace(minute=0)
    候補 = []
    while len(候補) <= 何本目:
        for m in 分:
            c = t.replace(minute=m)
            if c >= t:
                候補.append(c)
        t = (t + timedelta(hours=1)).replace(minute=0)
    return 候補[何本目].isoformat()


def 返事を入れる(mine: list[dict], repo: Path) -> list[str]:
    出す = [a for a in mine if a.get("種類") == "返事の案" and a.get("答え") == "出す"]
    if not 出す:
        return []
    q = repo / "posts" / "queue.jsonl"
    すでに = {json.loads(l).get("id") for l in q.read_text(encoding="utf-8").splitlines() if l.strip()} if q.exists() else set()
    今 = datetime.now(JST)
    済み, 行たち = [], []
    for a in 出す:
        文 = str(a.get("返事") or "").strip()
        宛先 = str(a.get("reply_to") or "").strip()
        if not 文 or not 宛先.isdigit() or len(文) > 500:
            print(f"::warning::返事の案 {a.get('id')} は、返事の文か宛先の ID が無いので入れません")
            continue
        pid = f"r-{今:%Y%m%d}-{a['id'][:8]}"
        if pid not in すでに:
            承認 = str(a.get("答えた時刻") or a.get("答えた日") or 今.isoformat(timespec="seconds"))
            行 = {"id": pid, "text": 文, "scheduled_at": 返事の時刻(今, len(行たち)), "approved_at": 承認}
            # エキマエのキューは reply_to_id（エキマエ開発の形）。おでかけは reply_to
            if a.get("出どころ") == "ふくいエキマエ":
                行["reply_to_id"] = 宛先
            else:
                行["reply_to"] = 宛先
                行["note"] = "読者の返信への返事（代表が判断待ちで「出す」）"
            行たち.append(json.dumps(行, ensure_ascii=False))
        済み.append(a["id"])
    if 行たち:
        with q.open("a", encoding="utf-8") as f:
            f.write("\n".join(行たち) + "\n")
    return 済み


def 反映(answers: list[dict], repos: dict[str, Path]) -> list[str]:
    名で = {v: k for k, v in 出どころの名.items()}
    済み = []
    今日 = datetime.now(JST).date().isoformat()
    for 名, repo in repos.items():
        if not repo:
            continue
        済み += 返事を入れる([a for a in answers if 名で.get(a.get("出どころ")) == 名], repo)
        if 名 == "ekimae":
            continue  # エキマエは返事だけ（ネタ帳は無い）
        mine = [a for a in answers if 名で.get(a.get("出どころ")) == 名 and a.get("答え") in ("載せる", "載せない")
                and a.get("種類") != "返事の案"]
        if not mine:
            continue
        ネタ帳p = repo / "neta" / "ネタ帳.md"
        ネタ帳 = ネタ帳p.read_text(encoding="utf-8")
        載せる行 = []
        for a in [a for a in mine if a["答え"] == "載せる"]:
            一言 = str(a.get("一言") or "").strip()
            行 = f"- 【代表：載せる】{a['中身']}" + (f" {a['url']}" if a.get("url") else "") + (f"（代表の一言：{一言}）" if 一言 else "")
            載せる行.append(行)
        if 載せる行:
            ネタ帳p.write_text(_調べもの節に足す(ネタ帳, 載せる行), encoding="utf-8")
        載せない = [a for a in mine if a["答え"] == "載せない"]
        if 載せない:
            p = repo / "neta" / "載せないもの.jsonl"
            with p.open("a", encoding="utf-8") as f:
                for a in 載せない:
                    f.write(json.dumps({"日": 今日, "中身": a["中身"], "url": a.get("url", ""), "一言": a.get("一言", "")},
                                       ensure_ascii=False) + "\n")
        済み += [a["id"] for a in mine]
    return 済み


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("やること", choices=["集める", "反映"])
    ap.add_argument("answers", nargs="?")
    ap.add_argument("--fukui", type=Path)
    ap.add_argument("--ishikawa", type=Path)
    ap.add_argument("--ekimae", type=Path, help="エキマエのリポジトリ（返事の案だけ）")
    a = ap.parse_args()
    repos = {"fukui": a.fukui, "ishikawa": a.ishikawa, "ekimae": a.ekimae}
    if a.やること == "集める":
        print(json.dumps(集める(repos), ensure_ascii=False, indent=1))
    else:
        answers = json.loads(Path(a.answers).read_text(encoding="utf-8"))
        print(json.dumps(反映(answers, repos), ensure_ascii=False))


if __name__ == "__main__":
    main()
