"""ネタ帳から、おでかけサイト用のデータを作る。

neta/ネタ帳.md の「書き足す場所」にある箇条書きを 1 件ずつ読み、
日付・エリア・種類・出典を取り出して docs/odekake/data.json に書き出す。
サイト（docs/odekake/index.html）はこの JSON を読むだけ。

    python scripts/おでかけ.py            # 書き出す
    python scripts/おでかけ.py --thumbs   # 出典ページのリンクカード（OG）も取りに行く
    python scripts/おでかけ.py --check    # 書き出さずに件数だけ見る

日付の読み取りは本文の書き方に頼った推測なので、読めなかったものは
「日付なし」として残す（捨てない）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

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


# ネタ帳の行末に付く公式 Instagram の印。収集はアカウントの URL を、人が手で足すときは
# 投稿やリールの URL を入れてもよい（サイトでは投稿を公式の埋め込みで出す）。
INSTAGRAM_MARK = re.compile(r"\s*［Instagram:\s*(https?://(?:www\.)?instagram\.com/[^\s］]+)\s*］")


def split_instagram(line: str) -> tuple[str, str | None]:
    """行から［Instagram: URL］を外し、(残りの行, URL) を返す。URL の ? 以降は捨てる。"""
    m = INSTAGRAM_MARK.search(line)
    if not m:
        return line, None
    url = m.group(1).split("?")[0]
    return (line[: m.start()] + line[m.end():]).strip(), url


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
            line, instagram = split_instagram(line)
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
                "instagram": instagram,
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


# リンクカード（OG）を取りに行かない出典。Instagram などは画像 URL が期限付きですぐ切れ、
# ログインを求められて中身も取れない。サイト名だけのカードにする。
NO_OG_HOSTS = ("instagram.com", "facebook.com", "x.com", "twitter.com", "threads.com", "threads.net")

# サイト共通のロゴや既定の OG 画像。どの記事にも同じ絵が出るだけなので使わない。
# WordPress の uploads に置かれたものは記事ごとの画像のことが多いので、ロゴ類だけ除く。
GENERIC_IMAGE = re.compile(r"logo|cropped-|site[-_]?icon|no[-_]?image", re.I)
GENERIC_OUTSIDE_UPLOADS = re.compile(r"ogp|og[-_]?im(age|g)|fb_ogp|/shared/|/common/|default", re.I)

OG_TITLE_MAX = 80
OG_DESC_MAX = 100


def is_generic_image(path: str) -> bool:
    if GENERIC_IMAGE.search(path):
        return True
    return "/uploads/" not in path and bool(GENERIC_OUTSIDE_UPLOADS.search(path))


_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r"""([a-zA-Z:_-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _metas(html: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for tag in _META.findall(html):
        attrs = {k.lower(): v.strip("\"'") for k, v in _ATTR.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and attrs.get("content", "").strip():
            found.setdefault(key, unescape(attrs["content"]).strip())
    return found


def _clip(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def find_og_image(html: str, page_url: str, metas: dict[str, str] | None = None) -> str | None:
    """HTML から og:image（なければ twitter:image）を取り出し、絶対 URL にする。"""
    metas = _metas(html) if metas is None else metas
    for key in ("og:image:secure_url", "og:image", "og:image:url", "twitter:image"):
        if key in metas:
            url = urljoin(page_url, metas[key])
            if not url.startswith(("https://", "http://")):
                return None
            return None if is_generic_image(urlparse(url).path) else url
    return None


def parse_og(html: str, page_url: str) -> dict | None:
    """リンクカードに出すもの（画像・タイトル・説明・サイト名）を取り出す。

    SNS のリンクプレビューと同じく、出典ページが共有用に用意した情報だけを使う。
    説明は長くなりすぎないように切る。何も取れなければ None。
    """
    metas = _metas(html)
    title = metas.get("og:title") or metas.get("twitter:title")
    if not title:
        m = _TITLE.search(html)
        title = unescape(m.group(1)) if m else None
    og = {
        "image": find_og_image(html, page_url, metas),
        "title": _clip(title, OG_TITLE_MAX),
        "description": _clip(metas.get("og:description") or metas.get("description")
                             or metas.get("twitter:description"), OG_DESC_MAX),
        "site": _clip(metas.get("og:site_name"), 40),
    }
    return og if any(og.values()) else None


def fetch_html(url: str, timeout: float = 15) -> str:
    req = urllib.request.Request(url, headers={
        # 独自の UA だと 403 を返す自治体サイトがあるので、ふつうのブラウザを名乗る
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept-Language": "ja",
    })
    with urllib.request.urlopen(req, timeout=timeout) as res:
        # 頭の部分に meta があるので、全部は読まない
        raw = res.read(400_000)
        charset = res.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def attach_og(items: list[dict], previous: dict[str, dict | None], fetch=fetch_html) -> int:
    """各項目に出典のリンクカード情報（og）を付ける。前回取れたもの（取れなかったものも）は使い回す。

    previous は 出典 URL → og（取れなかったら None）。通信に失敗したものは
    覚えずに次回また試す。新しく取りに行った件数を返す。
    """
    fetched = 0
    for it in items:
        src = it.get("source")
        if not src:
            it["og"] = None
            continue
        if src in previous:
            it["og"] = previous[src]
            continue
        host = urlparse(src).hostname or ""
        if any(host == h or host.endswith("." + h) for h in NO_OG_HOSTS):
            it["og"] = None
            continue
        try:
            it["og"] = parse_og(fetch(src), src)
        except urllib.error.HTTPError as e:
            if not 400 <= e.code < 500:
                print(f"  リンクカードの取得に失敗（次回また試す）: {src} — {e}", file=sys.stderr)
                continue
            # ページが無い・断られた：何度試しても同じなので、無しとして覚える
            print(f"  リンクカードなし（{e.code}）: {src}", file=sys.stderr)
            it["og"] = None
        except Exception as e:  # noqa: BLE001 — 1 件の失敗で全体を止めない
            print(f"  リンクカードの取得に失敗（次回また試す）: {src} — {e}", file=sys.stderr)
            continue  # og キーを付けない = 覚えない
        previous[src] = it["og"]
        fetched += 1
    return fetched


def load_previous_og(path: Path) -> dict[str, dict | None]:
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {it["source"]: it["og"] for it in old.get("items", [])
            if it.get("source") and "og" in it}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="書き出さずに件数だけ表示する")
    ap.add_argument("--thumbs", action="store_true", help="出典ページのリンクカード（OG）を取りに行く")
    args = ap.parse_args(argv)

    data = build(NETA.read_text(encoding="utf-8"))
    items = data["items"]
    previous = load_previous_og(OUT)
    if args.thumbs:
        n = attach_og(items, previous)
        print(f"リンクカード: 新しく {n} 件を取りに行った")
    else:
        # 取りに行かないときも、前回取れたものは残す
        for it in items:
            if it.get("source") in previous:
                it["og"] = previous[it["source"]]
    with_og = [i for i in items if i.get("og")]
    print(f"リンクカードあり {len(with_og)} 件（うち画像あり {sum(1 for i in with_og if i['og'].get('image'))} 件）")
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
