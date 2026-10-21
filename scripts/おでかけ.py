"""ネタ帳から、おでかけサイト用のデータを作る。

neta/ネタ帳.md の「書き足す場所」にある箇条書きを 1 件ずつ読み、
日付・エリア・種類・出典を取り出して docs/data.json に書き出す。
サイト（docs/index.html）はこの JSON を読むだけ。

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
from datetime import date, timedelta
from urllib.parse import quote
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import 地域  # noqa: E402  どの県のおでかけか（region.json）

KEN = 地域.県名
SITE_NAME = 地域.地域["サイト名"]
ACCOUNT = 地域.地域["アカウント"]
NETA = ROOT / "neta" / "ネタ帳.md"
OUT = ROOT / "docs" / "data.json"

# 地名・施設名 → 市町。本文の中でいちばん前に出てくるものを採る（region.json の「地名」）。
AREAS = [tuple(x) for x in 地域.地域["地名"]]

SPOT_WORDS = ("オープン", "開業", "新店", "グランドオープン", "リニューアル", "出店")
EVENT_WORDS = ("開催", "まつり", "祭", "フェス", "展", "イベント", "マルシェ",
               "フェア", "ツアー", "体験", "募集", "公開", "ライブ", "開館")

# 曜日のかっこは半角・全角どちらも（ぎふあいちの収集は「10/10（土）〜18（日）」と書く。2026-10-15）
_DOW = r"(?:\s*[(（][月火水木金土日祝・]+[)）])?"
_MD = r"(\d{1,2})/(\d{1,2})" + _DOW
# 9/26-10/12、10/3-4、9/10〜11/3 のような期間
RANGE = re.compile(_MD + r"\s*[-〜～－–]\s*(?:(\d{1,2})/)?(\d{1,2})(?!\d)")
SINGLE = re.compile(_MD)
# 「10/17・18」「10/24（土）・25（日）」のように、同じ月の日だけを「・」で続けたもの
SAME_MONTH_DAYS = re.compile(r"\s*・\s*(\d{1,2})(?![\d/])" + _DOW)
# 「11/29まで」「12月6日まで」のように終わりだけ書いたもの。始まりは書いた日とみなす
UNTIL = re.compile(r"^\s*(?:まで|迄)")
JP_DATE = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")
# 「10/17・24・31」「10/18(日)と10/25(日)」「11月7日・8日」のように、日を「・」「と」で並べたもの
DISCRETE = re.compile(r"(\d{1,2})/(\d{1,2})(?!\d)" + _DOW + r"((?:\s*[・と]\s*(?:\d{1,2}/)?\d{1,2}(?![\d/])" + _DOW + r")+)")
JP_DISCRETE = re.compile(r"(\d{1,2})月(\d{1,2})日" + _DOW + r"((?:\s*[・と]\s*(?:\d{1,2}月)?\d{1,2}日" + _DOW + r")+)")
JP_SAME_MONTH_DAYS = re.compile(r"\s*・\s*(\d{1,2})日" + _DOW)


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


def discrete_days(text: str, base: date) -> list[date]:
    """「10/17・24・31」のように飛び飛びの日を並べた書き方から、その日を返す。無ければ []。

    期間（10/17〜10/31）と別に、開く日だけを出すため（2026-10-20 SEO 調査：期間として出ていた）。
    続いている日（10/17・18）は期間のままでよいので [] を返す。
    """
    for pat, sep in ((DISCRETE, "/"), (JP_DISCRETE, "月")):
        m = pat.search(text)
        if not m:
            continue
        month = int(m.group(1))
        out = [_mk(_year_for(month, base), month, int(m.group(2)))]
        for part in re.finditer(r"(?:(\d{1,2})" + sep + r")?(\d{1,2})", re.sub(r"[(（][^)）]*[)）]", "", m.group(3))):
            if part.group(1):
                month = int(part.group(1))
            out.append(_mk(_year_for(month, base), month, int(part.group(2))))
        out = sorted({d for d in out if d})
        if len(out) >= 2 and (out[-1] - out[0]).days + 1 > len(out):
            return out
        return []
    return []


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

    until = False
    for m in SINGLE.finditer(text):
        month = int(m.group(1))
        dt = _mk(_year_for(month, base), month, int(m.group(2)))
        if dt:
            found.append(dt)
        pos = m.end()
        while n := SAME_MONTH_DAYS.match(text, pos):
            dt2 = _mk(_year_for(month, base), month, int(n.group(1)))
            if dt2:
                found.append(dt2)
            pos = n.end()
        until = until or bool(UNTIL.match(text[pos:]))
    if not found:
        for m in JP_DATE.finditer(text):
            y = int(m.group(1)) if m.group(1) else _year_for(int(m.group(2)), base)
            dt = _mk(y, int(m.group(2)), int(m.group(3)))
            if dt:
                found.append(dt)
            pos = m.end()
            # 「11月7日・8日」のように、同じ月の日を「・」で続けたもの（2026-10-20：8日が落ちていた）
            while n := JP_SAME_MONTH_DAYS.match(text, pos):
                dt2 = _mk(y, int(m.group(2)), int(n.group(1)))
                if dt2:
                    found.append(dt2)
                pos = n.end()
            until = until or bool(UNTIL.match(text[pos:]))
    if not found:
        return None, None
    if until and len(found) == 1 and base < found[0]:
        # 「◯日まで」だけのときは、書いた日から続いているものとして扱う
        return base, found[0]
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


THREADS_MARK = re.compile(r"\s*［Threads:\s*@[A-Za-z0-9._]+\s*］")


def split_instagram(line: str) -> tuple[str, str | None]:
    """行から［Instagram: URL］を外し、(残りの行, URL) を返す。URL の ? 以降は捨てる。"""
    m = INSTAGRAM_MARK.search(line)
    if not m:
        return line, None
    url = m.group(1).split("?")[0]
    # アプリの共有で付く /reels/（複数形）は、埋め込みに使える /reel/ にそろえる
    url = re.sub(r"instagram\.com/reels/", "instagram.com/reel/", url)
    return (line[: m.start()] + line[m.end():]).strip(), url


def split_note(line: str) -> tuple[str, str]:
    """「本文（→ ひとこと）」を本文とひとことに分ける。"""
    m = re.search(r"（→\s*(.+?)）\s*$", line)
    if not m:
        return line.strip(), ""
    return line[: m.start()].strip(), m.group(1).strip()


# 行の中に書いた出典「［出典: 名前 https://… ・ https://…］」（2026-10 から運用部がこの形で書く）。
# 本文から外して、最初の URL を出典にする（2026-10-20 SEO 調査：生の URL が本文に残り、スマホで横にはみ出していた）
INLINE_SOURCE = re.compile(r"\s*［出典[:：]\s*([^］]*)］")


def split_inline_source(line: str) -> tuple[str, str | None]:
    """行から［出典: …］を外し、(残りの行, 最初の URL) を返す。"""
    m = INLINE_SOURCE.search(line)
    if not m:
        return line, None
    url = re.search(r"https?://[^\s　、・）］]+", m.group(1))
    return (line[: m.start()] + line[m.end():]).strip(), url.group(0) if url else None


def parse_neta(md: str) -> list[dict]:
    """ネタ帳の「書き足す場所」から項目を取り出す。"""
    items: list[dict] = []
    section = md.split("## 書き足す場所", 1)
    if len(section) < 2:
        return items
    body = re.split(r"\n## ", section[1], maxsplit=1)[0]

    for block in re.split(r"\n(?=### )", body):
        head = re.match(r"### (\d{4})-(\d{2})-(\d{2})(.*)", block)
        if not head:
            continue
        written = date(int(head.group(1)), int(head.group(2)), int(head.group(3)))
        # 「### 2026-10-01（代表が見つけた催し）」のように、代表が手で足した欄はおすすめとして目立たせる
        pick = "代表" in head.group(4)
        main, _, rest = block.partition("<details>")
        bullets = [ln[2:].strip() for ln in main.splitlines() if ln.startswith("- ")]
        sources = re.findall(r"^- (https?://\S+)", rest, flags=re.M)
        # 出典は箇条書きと同じ順に並べる決まり。数が合わないときは結び付けない。
        paired = len(sources) == len(bullets)

        for i, line in enumerate(bullets):
            line, instagram = split_instagram(line)
            # 新店の公式 Threads の印（2026-10-13）は投稿で使うもの。サイトには出さない
            line = THREADS_MARK.sub("", line).strip()
            line, inline = split_inline_source(line)
            text, note = split_note(line)
            start, end = parse_dates(text, written)
            days = discrete_days(text, written)
            items.append({
                "text": text,
                "note": note,
                "kind": guess_kind(text),
                "area": guess_area(text),
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
                # 飛び飛びの日（「10/17・24・31」）。続いている日（10/17・18）は期間のままでよいので入れない
                **({"days": [d.isoformat() for d in days]} if days else {}),
                "source": inline or (sources[i] if paired else None),
                "instagram": instagram,
                "written": written.isoformat(),
                "pick": pick,
            })

    # 同じ本文が二度入っていたら、新しく書いたほうを残す
    seen: set[str] = set()
    unique = []
    for it in sorted(items, key=lambda x: x["written"], reverse=True):
        if it["text"] in seen:
            continue
        seen.add(it["text"])
        unique.append(it)
    return _merge_same_event(unique)


def _merge_same_event(items: list[dict]) -> list[dict]:
    """書き方の違う同じ催しを1件にまとめる（2026-10-20 SEO 調査 ⑤：サイトに2回出ていた）。

    - 名前と日付（始まり・終わり）が同じもの → 新しく書いたほうを残す（items は新しい順）
    - 日付の無い行と、同じ名前の日付のある行 → 日付のある行を残す（案内の段階で書いた行が残っていた）
    名前が同じでも日付の違うもの（毎月のマルシェなど）は別の催しとして残す。
    """
    dated = {_title(it) for it in items if it["start"]}
    seen: set[tuple] = set()
    out = []
    for it in items:
        name = _title(it)
        if not it["start"] and name in dated:
            continue
        key = (name, it["start"], it["end"])
        if it["start"] and key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def build(md: str) -> dict:
    items = parse_neta(md)
    for it in items:
        it["region"] = 地域.地区(it["area"])
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


# ---- 検索エンジン向けの静的な中身（2026-10-04 SEO 第1段階） ----
# サイトは JavaScript で描くので、HTML だけを読む検索エンジンには中身が見えない。
# index.html の目印のあいだに、これからの催しと新しい場所を素の HTML で書き込む
# （ブラウザでは JavaScript がこの部分を描き直す）。sitemap.xml もここで作る。
SITE = 地域.サイトURL
INDEX = ROOT / "docs" / "index.html"
SITEMAP = ROOT / "docs" / "sitemap.xml"
MARK_START, MARK_END = "<!--prerender:start-->", "<!--prerender:end-->"
WD = "月火水木金土日"


def _title(it: dict) -> str:
    # 「」が複数あるときは、「…」が／を／開催 のように主語になっているものを採る。
    # 「道の駅『若狭美浜はまびより』内に『美ton』が…」で場所の名前が見出しになっていた（2026-10-20）
    # 見るのは最初の一文だけ（後ろの文の「おがくず」などを拾わない）。「けれんしあ。」のように「」の中の。は文の終わりにしない
    first = re.match(r"(?:「[^」]*」|[^。「])*", it["text"]).group(0)
    qs = list(re.finditer(r"「([^」]{2,40})」", first))
    if not qs:
        m = re.search(r"「([^」]{2,40})」", it["text"])
        if m:
            return m.group(1)
    for m in qs:
        after = re.sub(r"^[（(][^）)]*[）)]", "", it["text"][m.end():])
        if re.match(r"(?:が|を|は|開催|オープン|新オープン)", after):
            return m.group(1)
    for m in qs:
        after = it["text"][m.end():]
        # 「◯◯」内に／にケンタッキー… のような場所の名前は見出しにしない
        if not re.match(r"(?:内|に|で|前|近く|周辺)", after):
            return m.group(1)
    # 「」が無いときは、先頭の日付（10/3-4 など）を外した最初の一文
    head = re.sub(r"^\s*" + _MD + r"(?:\s*[-〜～－–]\s*(?:\d{1,2}/)?\d{1,2})?\s*", "", it["text"])
    return head.split("。")[0][:44]


def _when(it: dict) -> str:
    if not it.get("start"):
        return ""
    s = date.fromisoformat(it["start"])
    e = date.fromisoformat(it["end"]) if it.get("end") else s
    f = lambda d: f"{d.month}月{d.day}日（{WD[d.weekday()]}）"
    if it["kind"] == "スポット":
        return f"{s.year}年{s.month}月{s.day}日オープン"
    if it.get("days"):
        ds = [date.fromisoformat(x) for x in it["days"]]
        return "・".join(f(d) if i == 0 or d.month != ds[i - 1].month else f"{d.day}日（{WD[d.weekday()]}）" for i, d in enumerate(ds))
    return f(s) if s == e else f"{f(s)}〜{f(e)}"


def _card(it: dict) -> str:
    from html import escape as h
    meta = "・".join(x for x in (_when(it), it.get("area") or "") if x)
    out = [f'<article><h3>{h(_title(it))}</h3>']
    if meta:
        out.append(f"<p>{h(meta)}</p>")
    out.append(f"<p>{h(it['text'])}</p>")
    if it.get("note"):
        out.append(f"<p>{h(it['note'])}</p>")
    if it.get("source"):
        out.append(f'<p><a href="{h(it["source"])}" rel="noopener">出典</a></p>')
    out.append("</article>")
    return "".join(out)


def prerender(data: dict, today: date, limit_events: int = 40, limit_spots: int = 15) -> str:
    items = data["items"]
    alive = lambda it: it.get("end") and date.fromisoformat(it["end"]) >= today
    events = sorted((it for it in items if it["kind"] == "催し" and alive(it)), key=lambda it: it["start"])
    spots = sorted((it for it in items if it["kind"] == "スポット" and it.get("start")),
                   key=lambda it: it["start"], reverse=True)
    parts = [MARK_START, '<div class="prerender">']
    parts.append(f"<h2>開催中・これからの{KEN}のイベント（{today.month}月{today.day}日時点）</h2>")
    parts += [_card(it) for it in events[:limit_events]]
    parts.append(f"<h2>{KEN}に新しくできたお店・スポット</h2>")
    parts += [_card(it) for it in spots[:limit_spots]]
    parts.append("</div>")
    parts.append(MARK_END)
    return "\n".join(parts)


# ---- 月別ページ（2026-10-04 SEO 第2段階） ----
# 「福井 イベント 10月」のような検索を受けるページ。中身の薄いページを量産しないよう、
# 今月以降で、短い催しが MONTH_MIN 件以上ある月だけ作る。一度作った月のページは、月が過ぎても残して
# 作り直す（2026-10-20 代表：検索で来る人のほとんどが月のページから。消すと積み上げた評価がなくなる）。
MONTH_DIR = ROOT / "docs" / "month"
MONTH_MIN = 5
MONTHS_MARK = ("<!--months:start-->", "<!--months:end-->")
_CF = 地域.地域.get("Cloudflare", "")
_GA = 地域.地域.get("GA", "")
CF_BEACON = ((('<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" '
              f'data-cf-beacon=\'{{"token": "{_CF}"}}\'></script>') if _CF else "")
             + ((f'<script async src="https://www.googletagmanager.com/gtag/js?id={_GA}"></script>'
                 '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
                 f'gtag("js",new Date());gtag("config","{_GA}");</script>') if _GA else ""))
# 月ごとの冒頭の一言（手で書いたもの。年をまたいでも使える季節の話だけにする）
MONTH_NOTE = {
    1: "雪の季節。屋内の展示や、冬ならではの味覚の催しが中心になります。",
    2: "まだ雪の残る時期。冬の祭りや、春を待つ催しが少しずつ始まります。",
    3: "雪がとけて、外の催しが戻ってくる季節。年度替わりの新しいお店も増えます。",
    4: "桜の季節。足羽川の桜並木をはじめ、花見に合わせた催しが県内各地で開かれます。",
    5: "新緑の行楽シーズン。連休のイベントや、外で楽しむマルシェが増えます。",
    6: "梅雨入りの時期。屋内の展示や、初夏の味覚を楽しむ催しが中心になります。",
    7: "夏祭りと海開きの季節。花火大会や海辺のイベントが続きます。",
    8: "夏祭り・花火大会の本番。お盆の帰省に合わせた催しも多い月です。",
    9: "暑さがやわらぎ、秋の祭りやフェスが増えてくる季節です。",
    10: "行楽の秋。新そばや秋の味覚の催し、音楽フェスやマルシェが週末ごとに続きます。",
    11: "紅葉と冬の味覚の季節。越前がにの解禁を待つ時期で、食の催しが増えます。",
    12: "冬のはじまり。クリスマスや年末の催し、イルミネーションが中心になります。",
}
# 県ごとの一言があれば、そちらを使う（region.json の「月の一言」。キーは "1"〜"12"）
MONTH_NOTE.update({int(k): v for k, v in 地域.地域.get("月の一言", {}).items()})


def _span(it: dict) -> tuple[date, date] | None:
    if it["kind"] != "催し" or not it.get("start"):
        return None
    s = date.fromisoformat(it["start"])
    return s, date.fromisoformat(it["end"]) if it.get("end") else s


def _is_long(sp: tuple[date, date]) -> bool:
    return (sp[1] - sp[0]).days >= 7


def month_pages(data: dict, today: date, keep: set[str] = frozenset()) -> dict[str, dict]:
    """作る月 → {"short": [...], "long": [...]}。今月以降（と keep の月）で短い催しが MONTH_MIN 件以上の月だけ。"""
    out: dict[str, dict] = {}
    for it in data["items"]:
        sp = _span(it)
        if not sp:
            continue
        y, m = sp[0].year, sp[0].month
        while (y, m) <= (sp[1].year, sp[1].month):
            if (y, m) >= (today.year, today.month) or f"{y}-{m:02d}" in keep:
                b = out.setdefault(f"{y}-{m:02d}", {"short": [], "long": []})
                b["long" if _is_long(sp) else "short"].append(it)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return {k: v for k, v in sorted(out.items()) if len(v["short"]) >= MONTH_MIN}


def _month_label(key: str) -> str:
    y, m = key.split("-")
    return f"{int(y)}年{int(m)}月"


def _anchor(it: dict) -> str:
    """催し1件ごとのページ内リンク（#e-…）。本文から作るので、毎朝作り直しても変わらない。"""
    import hashlib
    return "e-" + hashlib.sha1(it["text"].encode("utf-8")).hexdigest()[:8]


def _event_ld(it: dict, page_url: str) -> dict:
    """構造化データの Event。書くのはネタ帳にある事実（名前・日付・市町・出典）だけ。"""
    sp = _span(it)
    region = f"{KEN}県" if "・" not in KEN else None
    addr = {"@type": "PostalAddress", "addressCountry": "JP"}
    if it.get("area"):
        addr["addressLocality"] = it["area"]
    if region:
        addr["addressRegion"] = region
    ev = {
        "@type": "Event",
        "name": _title(it),
        "startDate": sp[0].isoformat(),
        "endDate": sp[1].isoformat(),
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {"@type": "Place", "name": it.get("area") or KEN, "address": addr},
        "description": it["text"][:200],
        "url": f"{page_url}#{_anchor(it)}",
    }
    if it.get("source"):
        ev["sameAs"] = it["source"]
    return ev


def _page_card(it: dict, today: date) -> str:
    """月のページ・今週末のページの催し1件。"""
    from html import escape as h
    sp = _span(it)
    ended = bool(sp) and sp[1] < today   # 新店（スポット）には終わりが無い
    meta = "・".join(x for x in (_when(it), it.get("area") or "") if x)
    site = (it.get("og") or {}).get("site") or "出典"
    cls = ' class="ended"' if ended else ""
    mark = "<small>終了</small>" if ended else ""
    out = [f'<article id="{_anchor(it)}"{cls}><h3>{h(_title(it))}{mark}</h3>']
    if meta:
        out.append(f'<p class="meta">{h(meta)}</p>')
    out.append(f"<p>{h(it['text'])}</p>")
    if it.get("note"):
        out.append(f'<p class="note">{h(it["note"])}</p>')
    if it.get("source"):
        out.append(f'<p class="src"><a href="{h(it["source"])}" rel="noopener" target="_blank">{h(site)}で詳しく見る</a></p>')
    elif it.get("instagram"):
        out.append(f'<p class="src"><a href="{h(it["instagram"])}" rel="noopener" target="_blank">お店の Instagram を見る</a></p>')
    out.append("</article>")
    return "".join(out)


def _shell(title: str, desc: str, url: str, ld: str, main: str, up: str) -> str:
    """月のページ・今週末のページなどの外側（head・見た目・フッター）。up はトップへの相対パス。"""
    from html import escape as h
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{h(title)}</title>
<meta name="description" content="{h(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{h(title)}">
<meta property="og:description" content="{h(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:site_name" content="{h(SITE_NAME)}">
<meta property="og:locale" content="ja_JP">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{up}favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="{up}apple-touch-icon.png">
<meta name="theme-color" content="#1f7a57">
<script type="application/ld+json">{ld}</script>
<style>
:root {{ --bg: #f5f1e8; --surface: #fff; --ink: #22302a; --muted: #6d7570; --main: #1f7a57; --line: #e4ddcf; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #141815; --surface: #1d231f; --ink: #e8eee9; --muted: #a2aba5; --main: #4cc292; --line: #2e3631; }} }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif; line-height: 1.8; overflow-wrap: anywhere; }}
header {{ background: #1f7a57; color: #fff; padding: 14px 16px; }}
header a {{ color: #fff; text-decoration: none; font-weight: 700; }}
main {{ max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }}
h1 {{ font-size: 1.5rem; margin: 0 0 8px; }}
h2 {{ font-size: 1.05rem; margin: 30px 0 10px; padding-bottom: 6px; border-bottom: 2px dashed var(--line); }}
article {{ background: var(--surface); border-radius: 14px; padding: 12px 16px; margin: 10px 0; }}
article h3 {{ font-size: 1rem; margin: 0 0 4px; }}
article h3 small {{ margin-left: 8px; font-size: .72rem; color: var(--muted); border: 1px solid var(--line); border-radius: 99px; padding: 1px 8px; }}
article.ended {{ opacity: .6; }}
article p {{ margin: 4px 0; font-size: .92rem; }}
.meta {{ color: var(--main); font-weight: 700; font-size: .85rem; }}
.note, .muted {{ color: var(--muted); font-size: .85rem; }}
.src a {{ font-size: .85rem; }}
a {{ color: var(--main); }}
.lead {{ background: var(--surface); border-radius: 14px; padding: 12px 16px; }}
nav.months {{ margin-top: 36px; font-size: .9rem; }}
footer {{ color: var(--muted); font-size: .78rem; text-align: center; padding: 0 16px 32px; }}
form.f label {{ display: block; font-weight: 700; font-size: .9rem; margin: 16px 0 4px; }}
form.f label small {{ font-weight: 400; color: var(--muted); }}
form.f input[type=text], form.f input[type=email], form.f input[type=url], form.f input[type=date], form.f select, form.f textarea {{ width: 100%; font: inherit; padding: 10px 12px; border: 1.5px solid var(--line); border-radius: 10px; background: var(--surface); color: var(--ink); }}
form.f textarea {{ min-height: 9em; }}
form.f .check {{ display: flex; gap: 8px; align-items: flex-start; font-weight: 400; }}
form.f .check input {{ margin-top: .45em; }}
form.f button {{ margin-top: 20px; font: inherit; font-weight: 700; background: var(--main); color: #fff; border: 0; border-radius: 999px; padding: 12px 28px; cursor: pointer; }}
form.f button:disabled {{ opacity: .5; }}
form.f .hp {{ position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }}
.msg {{ margin-top: 16px; padding: 12px 16px; border-radius: 12px; background: var(--surface); }}
.msg.err {{ border: 1.5px solid #d9473a; }}
form.f .req {{ color: #d9473a; font-weight: 800; margin: 0 4px 0 2px; flex: none; }}
form.f .reqnote {{ font-size: .85rem; color: var(--muted); margin: 8px 0 0; }}
.msg .rh {{ margin-top: 12px; font-weight: 700; }}
.msg dl.receipt {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; margin: 6px 0 0; font-size: .9rem; }}
.msg dl.receipt dt {{ color: var(--muted); }}
.msg dl.receipt dd {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }}
@media (max-width: 520px) {{ .msg dl.receipt {{ grid-template-columns: 1fr; gap: 0; }} .msg dl.receipt dd {{ margin-bottom: 6px; }} }}
form.f .paynote {{ margin: 20px 0 0; padding: 12px 14px; border: 2px solid var(--main); border-radius: 12px; background: var(--surface); font-weight: 700; }}
form.f .bad {{ border-color: #d9473a !important; outline: 2px solid #d9473a33; }}
form.f label.check.bad {{ border: 1.5px solid #d9473a; border-radius: 8px; padding: 4px 6px; }}
form.f .ferr {{ color: #d9473a; font-size: .85rem; font-weight: 700; margin: 4px 0 0; }}
form.f .flyer {{ margin-top: 20px; }}
form.f .flyer input[type=file] {{ position: absolute; width: 1px; height: 1px; opacity: 0; overflow: hidden; }}
form.f label.filebtn {{ display: flex; align-items: center; gap: 12px; margin: 0; min-height: 64px; padding: 14px 18px; border: 2px dashed var(--main); border-radius: 14px; background: color-mix(in srgb, var(--main) 10%, var(--surface)); color: var(--ink); font-size: 1.05rem; cursor: pointer; }}
form.f label.filebtn .ic {{ font-size: 1.6rem; line-height: 1; }}
form.f label.filebtn small {{ display: block; font-size: .8rem; }}
form.f .flyer input[type=file]:focus-visible + label.filebtn {{ outline: 3px solid var(--main); outline-offset: 2px; }}
form.f .picked {{ display: flex; align-items: center; gap: 12px; margin-top: 8px; padding: 10px 12px; border: 1.5px solid var(--line); border-radius: 12px; background: var(--surface); }}
form.f .picked[hidden] {{ display: none; }}
form.f .picked img {{ width: 64px; height: 64px; object-fit: cover; border-radius: 8px; flex: none; }}
form.f .picked .pdf {{ width: 64px; height: 64px; display: grid; place-items: center; border-radius: 8px; background: var(--bg); font-weight: 800; flex: none; }}
form.f .picked .nm {{ flex: 1; min-width: 0; font-size: .9rem; overflow-wrap: anywhere; }}
form.f button.clear {{ margin: 0; padding: 8px 14px; background: transparent; color: var(--ink); border: 1.5px solid var(--line); font-weight: 600; }}
table.toku {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 14px; overflow: hidden; margin-top: 16px; font-size: .92rem; }}
table.toku th, table.toku td {{ text-align: left; vertical-align: top; padding: 10px 14px; border-bottom: 1px solid var(--line); }}
table.toku th {{ width: 34%; color: var(--muted); font-weight: 700; }}
@media (max-width: 520px) {{ table.toku th, table.toku td {{ display: block; width: auto; }} table.toku th {{ border-bottom: 0; padding-bottom: 0; }} }}
</style>
</head>
<body>
<header><a href="{up}">← {h(SITE_NAME)}</a></header>
<main>
{main}</main>
<footer>Threads <a href="https://www.threads.com/@{h(ACCOUNT)}" rel="noopener">@{h(ACCOUNT)}</a> が集めた{h(KEN)}の情報をまとめています。<br><a href="{up}about/">運営者情報・編集方針・プライバシー</a>{f' ・ <a href="{up}contact/">お問い合わせ</a>' if _uses("問い合わせ") else ""}{f' ・ <a href="{up}submit/">イベント掲載のお申し込み（主催者の方）</a>' if _uses("掲載申し込み") else ""}{f' ・ <a href="{up}tokushoho/">特定商取引法に基づく表記</a>' if _uses("特商法") else ""}</footer>
{CF_BEACON}
</body>
</html>
"""


def render_month(key: str, b: dict, keys: list[str], today: date) -> str:
    from collections import Counter
    from html import escape as h
    y, m = map(int, key.split("-"))
    label = _month_label(key)
    first = date(y, m, 1)
    short = sorted(b["short"], key=lambda it: (it["start"], _title(it)))
    long_ = sorted(b["long"], key=lambda it: it["end"])
    areas = Counter(it.get("area") for it in short + long_ if it.get("area")).most_common(3)
    area_txt = "、".join(f"{a}（{n}件）" for a, n in areas)
    url = f"{SITE}/month/{key}/"
    title = f"{KEN}のイベント {label}｜{SITE_NAME}"
    past = (y, m) < (today.year, today.month)
    desc = (f"{label}に{KEN}県内で{'開かれた' if past else '開かれる'}イベント・祭り・マルシェ・展示を日付順にまとめました。"
            f"全{len(short) + len(long_)}件、主催者や自治体などの出典つき。")

    card = lambda it: _page_card(it, today)

    body = []
    days: dict[date, list] = {}
    for it in short:
        days.setdefault(max(_span(it)[0], first), []).append(it)
    for d, its in days.items():
        head = f"{d.month}月{d.day}日（{WD[d.weekday()]}）"
        if d == first and any(_span(i)[0] < first for i in its):
            head += "〜 先月から続く催しを含む"
        body.append(f"<h2>{h(head)}</h2>" + "".join(card(i) for i in its))
    if long_:
        body.append(f"<h2>{m}月の期間中に行ける展示・フェア</h2>"
                    "<p class=\"muted\">1週間以上つづく催しです。期間中の好きな日に行けます。</p>"
                    + "".join(card(i) for i in long_))
    nav = " ・ ".join(f'<a href="../{k}/">{_month_label(k)}</a>' if k != key else f"<b>{_month_label(k)}</b>" for k in keys)
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": f"{KEN}のイベント {label}", "item": url}]}
    # 催しの一覧（ItemList の中に Event）。Google のイベントの欄に出るように（2026-10-20 代表 OK）
    events = [{"@type": "ListItem", "position": n, "item": _event_ld(it, url)}
              for n, it in enumerate(short + long_, start=1)]
    graph = [crumbs] + ([{"@type": "ItemList", "name": f"{KEN}のイベント {label}", "numberOfItems": len(events),
                           "itemListElement": events}] if events else [])
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    main = f"""<h1>{h(KEN)}のイベント {h(label)}</h1>
<div class="lead">
<p>{h(MONTH_NOTE[m])}</p>
<p>{h(label)}に{h(KEN)}県内で開かれるイベントを、日付順にまとめました。1日〜数日の催しが{len(short)}件、期間中いつでも行ける展示・フェアが{len(long_)}件です。{h(f"多いのは{area_txt}。") if area_txt else ""}</p>
<p class="muted">日付・内容は集めた時点のものです。お出かけ前に、出典（主催者・自治体などの公式）で必ず確かめてください。最終更新：{today.year}年{today.month}月{today.day}日</p>
</div>
{"".join(body)}
<nav class="months">月別：{nav}</nav>
<p><a href="../../">今週末のイベント・新しいお店を見る（{h(SITE_NAME)}）</a></p>
"""
    return _shell(title, desc, url, ld, main, "../../")


# ---- 今週末のページ（2026-10-20 代表 OK、SEO の3） ----
# 「福井 イベント 今週末」を受けるページ。トップのボタンの切り替えには URL が無いので、静的に作る。
# 毎日作り直す（odekake.yml の schedule）。月〜金は次の土日、土日はその土日。
WEEKEND_DIR = ROOT / "docs" / "weekend"


def weekend_of(today: date) -> tuple[date, date]:
    sat = today + timedelta(days=(5 - today.weekday()) % 7) if today.weekday() != 6 else today - timedelta(days=1)
    return sat, sat + timedelta(days=1)


def _on(it: dict, d: date) -> bool:
    sp = _span(it)
    if not sp or not (sp[0] <= d <= sp[1]):
        return False
    return not it.get("days") or d.isoformat() in it["days"]


def render_weekend(data: dict, today: date) -> str:
    from html import escape as h
    sat, sun = weekend_of(today)
    evs = [it for it in data["items"] if it["kind"] != "スポット" and _span(it)]
    both = [it for it in evs if _on(it, sat) and _on(it, sun)]
    long_ = [it for it in both if _is_long(_span(it))]
    both = [it for it in both if not _is_long(_span(it))]
    only_sat = [it for it in evs if _on(it, sat) and not _on(it, sun)]
    only_sun = [it for it in evs if _on(it, sun) and not _on(it, sat)]
    key = lambda it: (_span(it)[0], _title(it))
    f = lambda d: f"{d.month}月{d.day}日（{WD[d.weekday()]}）"
    url = f"{SITE}/weekend/"
    n = len(both) + len(only_sat) + len(only_sun) + len(long_)
    title = f"今週末の{KEN}のイベント・おでかけ情報（{sat.month}/{sat.day}・{sun.day if sun.month == sat.month else f'{sun.month}/{sun.day}'}）｜{SITE_NAME}"
    desc = (f"{f(sat)}・{f(sun)}に{KEN}県内で行けるイベント・祭り・マルシェ・展示{n}件を、土曜・日曜・両日に分けてまとめました。"
            "毎日更新、主催者や自治体などの出典つき。")
    body = []
    for head, its in ((f"{f(sat)}・{f(sun)} の両日", both), (f"{f(sat)} だけ", only_sat),
                      (f"{f(sun)} だけ", only_sun)):
        if its:
            body.append(f"<h2>{h(head)}</h2>" + "".join(_page_card(i, today) for i in sorted(its, key=key)))
    if long_:
        body.append("<h2>期間中に行ける展示・フェア</h2><p class=\"muted\">1週間以上つづく催しです。</p>"
                    + "".join(_page_card(i, today) for i in sorted(long_, key=lambda it: _span(it)[1])))
    if not body:
        body.append("<p>この土日の催しは、まだ集まっていません。月別のページもご覧ください。</p>")
    months = sorted({f"{d.year}-{d.month:02d}" for d in (sat, sun)})
    links = " ・ ".join(f'<a href="../month/{k}/">{_month_label(k)}の{h(KEN)}のイベント</a>'
                       for k in months if (MONTH_DIR / k).is_dir())
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": f"今週末の{KEN}のイベント", "item": url}]}
    allev = sorted(both, key=key) + sorted(only_sat, key=key) + sorted(only_sun, key=key) + long_
    graph = [crumbs] + ([{"@type": "ItemList", "name": f"今週末の{KEN}のイベント", "numberOfItems": len(allev),
                           "itemListElement": [{"@type": "ListItem", "position": i, "item": _event_ld(it, url)}
                                               for i, it in enumerate(allev, start=1)]}] if allev else [])
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    main = f"""<h1>今週末の{h(KEN)}のイベント（{h(f(sat))}・{h(f(sun))}）</h1>
<div class="lead">
<p>この土日に{h(KEN)}県内で行けるイベントを、両日・土曜だけ・日曜だけに分けてまとめました。全{n}件です。</p>
<p class="muted">日付・内容は集めた時点のものです。お出かけ前に、出典（主催者・自治体などの公式）で必ず確かめてください。最終更新：{today.year}年{today.month}月{today.day}日</p>
</div>
{"".join(body)}
<nav class="months">{links}</nav>
<p><a href="../">新しいお店・ほかの日のイベントを見る（{h(SITE_NAME)}）</a></p>
"""
    return _shell(title, desc, url, ld, main, "../")


# ---- 新しいお店のページ（2026-10-20 代表 OK、SEO の4） ----
# 「福井 新店 オープン」を受けるページ。オープン日のある新店を、これから・月ごとに新しい順で並べる。
SPOT_DIR = ROOT / "docs" / "spot"
SPOT_MONTHS = 6   # 何か月前までのオープンを載せるか


def _shop_ld(it: dict, page_url: str) -> dict:
    """構造化データの LocalBusiness。書くのはネタ帳にある事実（名前・市町・オープン日・出典）だけ。"""
    addr = {"@type": "PostalAddress", "addressCountry": "JP"}
    if it.get("area"):
        addr["addressLocality"] = it["area"]
    if "・" not in KEN:
        addr["addressRegion"] = f"{KEN}県"
    ld = {"@type": "LocalBusiness", "name": _title(it), "address": addr,
          "description": it["text"][:200], "url": f"{page_url}#{_anchor(it)}"}
    if it.get("start"):
        ld["foundingDate"] = it["start"]
    same = [u for u in (it.get("source"), it.get("instagram")) if u]
    if same:
        ld["sameAs"] = same
    return ld


def render_spot(data: dict, today: date) -> str:
    from collections import Counter
    from html import escape as h
    y, m = today.year, today.month - SPOT_MONTHS
    while m < 1:
        y, m = y - 1, m + 12
    since = date(y, m, 1)
    shops = [it for it in data["items"] if it["kind"] == "スポット" and it.get("start")
             and date.fromisoformat(it["start"]) >= since]
    shops.sort(key=lambda it: (it["start"], _title(it)), reverse=True)
    soon = sorted((it for it in shops if date.fromisoformat(it["start"]) > today), key=lambda it: it["start"])
    groups: dict[str, list] = {}
    for it in shops:
        d = date.fromisoformat(it["start"])
        if d <= today:
            groups.setdefault(f"{d.year}年{d.month}月にオープン", []).append(it)
    url = f"{SITE}/spot/"
    title = f"{KEN}の新しいお店・新店オープン情報｜{SITE_NAME}"
    areas = [a for a, _ in Counter(it.get("area") for it in shops if it.get("area")).most_common(3)]
    desc = (f"{KEN}県内で新しくオープンしたお店・スポット{len(shops)}件を、オープン日の新しい順にまとめました。"
            + (f"{'・'.join(areas)}など。" if areas else "") + "お店の公式や自治体などの出典つき。")
    body = []
    if soon:
        body.append("<h2>これからオープン</h2>" + "".join(_page_card(i, today) for i in soon))
    for head, its in groups.items():
        body.append(f"<h2>{h(head)}</h2>" + "".join(_page_card(i, today) for i in its))
    if not body:
        body.append("<p>新しいお店の情報は、まだ集まっていません。</p>")
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": f"{KEN}の新しいお店", "item": url}]}
    allshops = soon + [i for its in groups.values() for i in its]
    graph = [crumbs] + ([{"@type": "ItemList", "name": f"{KEN}の新しいお店", "numberOfItems": len(allshops),
                           "itemListElement": [{"@type": "ListItem", "position": i, "item": _shop_ld(it, url)}
                                               for i, it in enumerate(allshops, start=1)]}] if allshops else [])
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    main = f"""<h1>{h(KEN)}の新しいお店・新店オープン情報</h1>
<div class="lead">
<p>{h(KEN)}県内で新しくオープンしたお店・スポットを、オープン日の新しい順にまとめました。ここ{SPOT_MONTHS}か月ほどの{len(shops)}件です。</p>
<p class="muted">営業時間・定休日などは集めた時点のものです。お出かけ前に、お店の公式で必ず確かめてください。最終更新：{today.year}年{today.month}月{today.day}日</p>
</div>
{"".join(body)}
<nav class="months"><a href="../weekend/">今週末の{h(KEN)}のイベント</a></nav>
<p><a href="../">イベント・おでかけ情報を見る（{h(SITE_NAME)}）</a></p>
"""
    return _shell(title, desc, url, ld, main, "../")


# ---- 市町別のページ（2026-10-20 代表 OK、SEO の5） ----
# 「金沢市 イベント」「坂井市 おでかけ」を受けるページ。URL は /area/金沢市/（日本語のまま。読み違いを避ける）。
# 中身の薄いページを増やさないよう、これからの催しと新しいお店が AREA_MIN 件以上ある市町だけ作る。
# 一度作ったページは、件数が減っても消さずに作り直す（月のページと同じ）。
AREA_DIR = ROOT / "docs" / "area"
AREA_MIN = 5


def _area_items(data: dict, today: date) -> dict[str, dict]:
    """市町 → {"events": [...], "shops": [...]}（終わった催しと、6か月より前の新店はのぞく）"""
    y, m = today.year, today.month - SPOT_MONTHS
    while m < 1:
        y, m = y - 1, m + 12
    since = date(y, m, 1)
    out: dict[str, dict] = {}
    for it in data["items"]:
        a = it.get("area")
        if not a:
            continue
        sp = _span(it)
        if sp and sp[1] >= today:
            out.setdefault(a, {"events": [], "shops": []})["events"].append(it)
        elif it["kind"] == "スポット" and it.get("start") and date.fromisoformat(it["start"]) >= since:
            out.setdefault(a, {"events": [], "shops": []})["shops"].append(it)
    return out


def render_area(area: str, b: dict, today: date) -> str:
    from html import escape as h
    from urllib.parse import quote
    sat, sun = weekend_of(today)
    evs = sorted(b["events"], key=lambda it: (_span(it)[0], _title(it)))
    wk = [it for it in evs if _on(it, sat) or _on(it, sun)]
    long_ = [it for it in evs if it not in wk and _is_long(_span(it))]
    rest = [it for it in evs if it not in wk and it not in long_]
    shops = sorted(b["shops"], key=lambda it: it["start"], reverse=True)
    url = f"{SITE}/area/{quote(area)}/"
    n = len(evs) + len(shops)
    title = f"{area}のイベント・おでかけ情報と新しいお店｜{SITE_NAME}"
    desc = (f"{KEN}・{area}で開かれるイベント・祭り・マルシェ・展示と、新しくオープンしたお店を{n}件まとめました。"
            "毎日更新、主催者や自治体などの出典つき。")
    f = lambda d: f"{d.month}月{d.day}日（{WD[d.weekday()]}）"
    body = []
    for head, its in ((f"今週末（{f(sat)}・{f(sun)}）", wk), ("これからのイベント", rest),
                      ("期間中に行ける展示・フェア", long_), ("新しいお店", shops)):
        if its:
            body.append(f"<h2>{h(head)}</h2>" + "".join(_page_card(i, today) for i in its))
    if not body:
        body.append(f"<p>いまは{h(area)}の催しが載っていません。ほかの市町や月別のページもご覧ください。</p>")
    crumbs = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": f"{SITE}/"},
        {"@type": "ListItem", "position": 2, "name": f"{area}のイベント・おでかけ情報", "item": url}]}
    lst = [_event_ld(it, url) for it in wk + rest + long_] + [_shop_ld(it, url) for it in shops]
    graph = [crumbs] + ([{"@type": "ItemList", "name": f"{area}のイベント・新しいお店", "numberOfItems": len(lst),
                           "itemListElement": [{"@type": "ListItem", "position": i, "item": x}
                                               for i, x in enumerate(lst, start=1)]}] if lst else [])
    ld = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False).replace("</", "<\\/")
    main = f"""<h1>{h(area)}のイベント・おでかけ情報</h1>
<div class="lead">
<p>{h(KEN)}・{h(area)}で開かれるイベントと、新しくオープンしたお店をまとめました。これからの催しが{len(evs)}件、新しいお店が{len(shops)}件です。</p>
<p class="muted">日付・内容は集めた時点のものです。お出かけ前に、出典（主催者・自治体・お店の公式）で必ず確かめてください。最終更新：{today.year}年{today.month}月{today.day}日</p>
</div>
{"".join(body)}
<nav class="months"><a href="../../weekend/">今週末の{h(KEN)}のイベント</a> ・ <a href="../../spot/">{h(KEN)}の新しいお店</a></nav>
<p><a href="../../">{h(KEN)}のほかの市町のおでかけ情報を見る（{h(SITE_NAME)}）</a></p>
"""
    return _shell(title, desc, url, ld, main, "../../")


def write_areas(data: dict, today: date) -> list[str]:
    made = {d.name for d in AREA_DIR.iterdir() if d.is_dir()} if AREA_DIR.exists() else set()
    groups = _area_items(data, today)
    areas = sorted((a for a, b in groups.items() if len(b["events"]) + len(b["shops"]) >= AREA_MIN or a in made),
                   key=lambda a: -(len(groups.get(a, {}).get("events", [])) + len(groups.get(a, {}).get("shops", []))))
    areas += sorted(made - set(areas))
    for a in areas:
        (AREA_DIR / a).mkdir(parents=True, exist_ok=True)
        (AREA_DIR / a / "index.html").write_text(render_area(a, groups.get(a, {"events": [], "shops": []}), today),
                                                 encoding="utf-8")
    return areas


# ---- フォーム（2026-10-20 代表 B 案：サイトのフォーム → Supabase → ダッシュボードの「判断待ち」） ----
# 受け取りは Supabase の Edge Function odekake-form（ソースは supabase/functions/odekake-form）。
# ロボットよけ（Cloudflare Turnstile）は、region.json の "Turnstile"（サイトキー。公開してよい鍵）があるときだけ出す。
# 秘密鍵は代表が Supabase に直接登録する（リポジトリ・チャットに書かない）。
# 仮押さえ（region.json の 使う.仮押さえ）のときの申し込みページの説明（2026-10-20 代表）
HOLD_LEAD = ("<p>いただいた情報は、主催者などの公式の案内で確かめてから掲載します。</p>"
             "<p><b>送信すると、お支払い画面（Stripe）に移ります。</b>カードで 5,500円（税込）を仮押さえしますが、"
             "掲載が決まるまで確定しません。掲載できない場合は取り消し、料金は請求されません。</p>")
# 有料掲載で提供する内容（2026-10-20 代表の文。特商法の表記・申し込みフォームで同じ文を使う）
PAID_OFFER = (f"「{SITE_NAME}」PR枠への掲載（最長30日）、Threads での紹介（掲載を始めたとき・毎週1回・開催の前日と当日）、"
              "AI で作る紹介動画（1回）。表示や投稿には「PR」と付きます。")
FORM_URL = "https://zynxnpwwmrxzyljrsmbs.supabase.co/functions/v1/odekake-form"
CONTACT_DIR = ROOT / "docs" / "contact"
SUBMIT_DIR = ROOT / "docs" / "submit"
PRIVACY_FORM = ("フォームでいただいたお名前・メールアドレスは、ご連絡と掲載の確認のためだけに使い、公開や第三者への提供はしません。"
                "運営者だけが見られる場所に保存し、用件が済んで1年たったものは消します。")


def _uses(name: str) -> bool:
    return bool(地域.地域.get("使う", {}).get(name, False))


def _form_script(kind: str) -> str:
    """送信の JS。足りない欄・おかしい欄を、名前つきで欄のすぐ下と送信の下に出す（2026-10-20 代表「わかりにくい」）。
    必須の欄には「必須」の印。入力し終えた欄から確かめる。エラーのあとも入力とチラシは消さない。成功したらお礼を出す。"""
    sitekey = 地域.地域.get("Turnstile", "")
    ts = ('<div class="cf-turnstile" data-sitekey="' + sitekey + '" data-language="ja"></div>'
          '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>') if sitekey else ""
    done = ('"受け付けました。申込番号：" + (j.number || "") + "。公式の案内で確かめてから、メールでご連絡します。"'
            if kind == "submission" else '"送信しました。ありがとうございます。お返事が必要な内容には、メールでご連絡します。"')
    # 送信すると支払い画面に移ることを、ボタンのすぐ上で先に伝える（2026-10-21 代表「それでOK」の文）
    pay = ('<p class="paynote">送信すると、カードの確認画面に移ります。この時点では請求されず、'
           '掲載が決まってから 5,500円（税込）を請求します。</p>') if kind == "submission" and _uses("仮押さえ") else ""
    return ts + pay + f"""<button type="submit">送信する</button>
<div class="msg" id="msg" hidden></div>
</form>
<script>
(() => {{
  const f = document.getElementById("f"), msg = document.getElementById("msg");
  f.opened.value = Date.now();
  const say = (t, err) => {{ msg.hidden = false; msg.className = "msg" + (err ? " err" : ""); msg.replaceChildren();
    for (const line of [].concat(t)) {{ const p = document.createElement("div"); p.textContent = line; msg.append(p); }} }};
  const fields = [...f.querySelectorAll("input:not([type=hidden]),textarea,select")].filter((x) => !x.closest(".hp"));
  // 欄の名前（ラベルの文字から「（あれば…）」などの小さな字を除いたもの）
  const nameOf = (x) => {{
    const lab = x.id && f.querySelector(`label[for="${{x.id}}"]`) || x.closest("label");
    if (!lab) return "入力";
    const c = lab.cloneNode(true); c.querySelectorAll("small,.req,input").forEach((n) => n.remove());
    return c.textContent.trim().replace(/\s+/g, " ");
  }};
  // 必須の印：欄の名前の横に赤い「*」、フォームの上に「* は必須です」（2026-10-20 代表）
  for (const x of fields) if (x.required) {{
    const lab = x.id && f.querySelector(`label[for="${{x.id}}"]`) || x.closest("label");
    if (lab && !lab.querySelector(".req")) {{
      const r = document.createElement("span"); r.className = "req"; r.textContent = "*"; r.setAttribute("aria-label", "必須");
      const small = lab.querySelector("small");
      if (small && x.type !== "checkbox") small.before(r); else lab.append(r);
    }}
  }}
  {{ const n = document.createElement("p"); n.className = "reqnote"; const r = document.createElement("span"); r.className = "req"; r.textContent = "*";
    n.append(r, " は必須です"); f.prepend(n); }}
  const problem = (x) => {{
    const v = (x.value || "").trim(), n = nameOf(x);
    if (x.type === "checkbox") return x.required && !x.checked ? `「${{n}}」にチェックを入れてください` : "";
    if (x.type === "file") {{
      const file = x.files && x.files[0];
      if (!file) return "";
      if (file.size > 5 * 1024 * 1024) return `${{n}}は 5MB までです（いまは ${{(file.size / 1048576).toFixed(1)}}MB）`;
      if (!/\.(jpe?g|png|webp|pdf)$/i.test(file.name)) return `${{n}}は JPEG・PNG・WebP・PDF のどれかにしてください`;
      return "";
    }}
    if (x.required && !v) return x.tagName === "SELECT" ? `${{n}}を選んでください` : `${{n}}を入れてください`;
    if (!v) return "";
    if (x.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]{{2,}}$/.test(v)) return `${{n}}の形が正しくありません（例：name@example.com）`;
    if (x.type === "url" && !/^https?:\/\/\S+$/.test(v)) return `${{n}}は https:// から始まる URL を入れてください`;
    if (x.maxLength > 0 && v.length > x.maxLength) return `${{n}}は ${{x.maxLength}} 字までです`;
    return "";
  }};
  const mark = (x, text) => {{
    const box = x.type === "checkbox" ? x.closest("label") : x;
    let e = box.nextElementSibling;
    if (!(e && e.classList.contains("ferr"))) e = null;
    box.classList.toggle("bad", !!text);
    if (text) {{
      if (!e) {{ e = document.createElement("p"); e.className = "ferr"; box.after(e); }}
      e.textContent = text;
    }} else if (e) e.remove();
  }};
  const check = (x) => {{ const t = problem(x); mark(x, t); return t; }};
  // 入力し終えた欄から確かめる（触る前の欄は赤くしない）
  for (const x of fields) {{
    x.addEventListener(x.type === "checkbox" || x.type === "file" || x.tagName === "SELECT" ? "change" : "blur", () => check(x));
    x.addEventListener("input", () => {{ if (x.classList.contains("bad") || x.closest(".bad")) check(x); }});
  }}
  const fail = (lines, first) => {{
    say(["送れませんでした。次のところを確かめてください。", ...lines.map((t) => "・" + t)], true);
    if (first) {{ first.scrollIntoView({{ behavior: "smooth", block: "center" }}); setTimeout(() => first.focus({{ preventScroll: true }}), 300); }}
  }};
  const SERVER = {{ fast: "少し時間をおいて、もう一度送ってください。", many: "送信が続いています。1時間ほどおいてから送ってください。",
    robot: "ロボットよけの確認ができませんでした。もう一度「送信する」を押してください。", agree: "同意の欄にチェックを入れてください。",
    closed: "いまは受け付けていません。" }};
  f.addEventListener("submit", async (e) => {{
    e.preventDefault();
    const bad = fields.map((x) => [x, check(x)]).filter(([, t]) => t);
    if (bad.length) {{ fail(bad.map(([, t]) => t), bad[0][0]); return; }}
    const b = f.querySelector("button[type=submit]"); b.disabled = true; say("送っています…");
    try {{
      const r = await fetch("{FORM_URL}", {{ method: "POST", body: new FormData(f) }});
      const j = await r.json().catch(() => ({{}}));
      if (r.ok && j.ok && j.pay_url) {{
        // 仮押さえ：Stripe の支払い画面へ。戻ってきたら下の「戻ったとき」で受付を確かめる。
        // 入力はこの端末（このタブ）にだけ一時保存し、戻ったら控えを出す・やめたら埋め直す（2026-10-21 代表「入力した項目は残っていてほしい」）
        try {{
          const v = {{}}, list = [];
          for (const x of fields) {{
            if (x.type === "file") {{ const fl = x.files && x.files[0]; if (fl) list.push(["チラシ", fl.name]); continue; }}
            v[x.name] = x.type === "checkbox" ? x.checked : x.value;
            if (x.type !== "checkbox" && x.value.trim()) list.push([nameOf(x), x.value.trim()]);
          }}
          sessionStorage.setItem("odekake-form-" + j.number, JSON.stringify({{ v, list, flyer: list.some(([k]) => k === "チラシ") }}));
        }} catch (_) {{}}
        say("お支払い画面（Stripe）に移ります…");
        location.href = j.pay_url;
        return;
      }}
      if (r.ok && j.ok) {{
        f.querySelectorAll("input,textarea,select,button").forEach((x) => (x.disabled = true));
        say({done});
        return;
      }}
      // ロボットよけの印は1回しか使えないので、作り直してもう一度押せるようにする
      if (window.turnstile) try {{ window.turnstile.reset(); }} catch (_) {{}}
      if (j.field) {{
        const x = f.elements[j.field];
        const t = x && x.nodeType ? (problem(x) || `${{nameOf(x)}}を確かめてください`) : "入力を確かめてください（URL は4本まで）";
        if (x && x.nodeType) mark(x, t);
        fail([t], x && x.nodeType ? x : null);
      }} else say(SERVER[j.error] || "送れませんでした。時間をおいてお試しください。", true);
    }} catch (_) {{ say("送れませんでした。通信を確かめて、もう一度お試しください。", true); }}
    b.disabled = false;
  }});
  // 支払い画面から戻ったとき（?n=申込番号&s=…）／やめたとき（&cancel=1）。2026-10-21 代表の指摘で作り直し：
  // カード・0円（クーポン）・やめた・確認中 を分けて出す。確認中は3秒おきに確かめ直す。受付が済んだら入力の控えを出し、
  // 済んでいなければ入力を埋め直す。同じ結果を出したタブで開き直したときは、前の結果を出さずに空のフォームに戻す
  const q = new URLSearchParams(location.search);
  if (q.get("n")) {{
    const n = q.get("n"), key = "odekake-form-" + n, doneKey = "odekake-done-" + n;
    history.replaceState(null, "", location.pathname);
    let saved = null;
    try {{ saved = JSON.parse(sessionStorage.getItem(key) || "null"); }} catch (_) {{}}
    let shown = false;
    try {{ shown = !!sessionStorage.getItem(doneKey); }} catch (_) {{}}
    const refill = () => {{
      if (!saved) return;
      for (const x of fields) {{
        if (x.type === "file" || !(x.name in saved.v)) continue;
        if (x.type === "checkbox") x.checked = !!saved.v[x.name]; else x.value = saved.v[x.name];
      }}
    }};
    const flyerNote = saved && saved.flyer ? "チラシのファイルは、もう一度選び直してください（ページを移ると、選んだファイルは消えます）。" : "";
    const receipt = () => {{
      if (!saved || !saved.list.length) return;
      const h = document.createElement("div"); h.className = "rh"; h.textContent = "お申し込み内容の控え";
      const dl = document.createElement("dl"); dl.className = "receipt";
      for (const [k, v] of saved.list) {{ const dt = document.createElement("dt"); dt.textContent = k; const dd = document.createElement("dd"); dd.textContent = v; dl.append(dt, dd); }}
      msg.append(h, dl);
    }};
    if (shown) {{ /* 同じタブで開き直した：前の結果は出さない */ }}
    else if (q.get("cancel")) {{
      refill();
      say(["お支払いを済ませていないため、まだ受け付けていません。", "入力は元に戻しました。内容を確かめて、もう一度「送信する」を押してください。", flyerNote].filter(Boolean), true);
      msg.scrollIntoView({{ block: "center" }});
    }} else {{
      say("お申し込みを確かめています…");
      const ask = async () => {{
        const fd = new FormData(); fd.append("type", "confirm"); fd.append("n", n); fd.append("s", q.get("s") || "");
        const r = await fetch("{FORM_URL}", {{ method: "POST", body: fd }}); return r.json();
      }};
      (async () => {{
        let j = {{}};
        for (let i = 0; i < 6; i++) {{
          try {{ j = await ask(); }} catch (_) {{ j = {{}}; }}
          if (j.ok || (j.status && j.status !== "pending_payment")) break;
          await new Promise((res) => setTimeout(res, 3000));
        }}
        if (j.ok) {{
          f.querySelectorAll("input,textarea,select,button").forEach((x) => (x.disabled = true));
          say(["受け付けました。申込番号：" + j.number,
               j.free ? "クーポンのご利用で 0円です（請求はありません）。" : "カードで 5,500円（税込）を仮押さえしました。まだ請求されていません。",
               j.free ? "公式の案内で確かめ、掲載が決まったらメールでお知らせします。"
                      : "公式の案内で確かめ、掲載が決まったら確定してメールでお知らせします。掲載できない場合は取り消し、料金は請求されません。",
               "受付のメールをお送りしました。届かない場合は迷惑メールのフォルダもご覧ください。"]);
          receipt();
          try {{ sessionStorage.setItem(doneKey, "1"); sessionStorage.removeItem(key); }} catch (_) {{}}
          msg.scrollIntoView({{ block: "center" }});
        }} else {{
          refill();
          say(["受付の確認に時間がかかっています（申込番号：" + n + "）。",
               "受付のメールが届けば、お申し込みは完了しています。しばらくしても届かない場合は、お問い合わせから申込番号をお知らせください。",
               "入力は元に戻してあります。", flyerNote].filter(Boolean));
          msg.scrollIntoView({{ block: "center" }});
        }}
      }})();
    }}
  }}
}})();
</script>"""


def render_contact(today: date) -> str:
    from html import escape as h
    url = f"{SITE}/contact/"
    title = f"お問い合わせ｜{SITE_NAME}"
    desc = f"{SITE_NAME}への、内容の誤り・掲載の取り下げなどのお問い合わせフォームです。"
    main = f"""<h1>お問い合わせ</h1>
<div class="lead">
<p>内容の誤り、掲載の取り下げ、そのほかのご連絡はこちらからどうぞ。お返事が必要な内容には、メールでご連絡します。</p>
<p class="muted">{h(PRIVACY_FORM)}</p>
</div>
<form class="f" id="f" novalidate>
<input type="hidden" name="type" value="inquiry"><input type="hidden" name="opened" value="">
<div class="hp" aria-hidden="true"><label>空けておいてください<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
<label for="kind">ご用件</label>
<select id="kind" name="kind" required>
<option value="fix">内容の誤り</option><option value="remove">掲載の取り下げ</option>
<option value="paid">有料のイベント掲載について</option><option value="other" selected>そのほか</option>
</select>
<label for="name">お名前</label><input type="text" id="name" name="name" maxlength="100" required autocomplete="name">
<label for="email">メールアドレス</label><input type="email" id="email" name="email" maxlength="200" required autocomplete="email">
<label for="page">関係するページや催しの名前 <small>（あれば）</small></label><input type="text" id="page" name="page" maxlength="300">
<label for="message">内容 <small>（1000字まで）</small></label><textarea id="message" name="message" maxlength="1000" required></textarea>
<label class="check"><input type="checkbox" name="agree" value="1" required>上の個人情報の扱いに同意します</label>
{_form_script("inquiry")}
<p><a href="../about/">運営者情報・編集方針・プライバシー</a></p>
"""
    ld = json.dumps({"@context": "https://schema.org", "@type": "ContactPage", "name": title, "url": url}, ensure_ascii=False)
    return _shell(title, desc, url, ld, main, "../")


def render_submit(today: date) -> str:
    """イベント掲載（有料）の申し込み。特商法の表記が決まるまで公開しない（region.json の 使う.掲載申し込み）。"""
    from html import escape as h
    url = f"{SITE}/submit/"
    title = f"イベント掲載の申し込み｜{SITE_NAME}"
    desc = f"{SITE_NAME}へのイベント掲載（有料）の申し込みフォームです。主催者の方からのみ受け付けます。"
    main = f"""<h1>イベント掲載の申し込み</h1>
<div class="lead">
<p><b>主催者の方からのみ受け付けます。</b></p>
{HOLD_LEAD if _uses("仮押さえ") else '<p>いただいた情報は、主催者などの公式の案内で確かめてから掲載します。掲載できる場合は、お支払いのご案内をメールでお送りします。</p>'}
<p>掲載の内容：{h(PAID_OFFER)}料金は 1件 5,500円（税込）です。</p>
<p>お支払いのあとの返金は、原則できません。事情がある場合は、<a href="../contact/">お問い合わせ</a>から運営へご連絡ください。料金などは<a href="../tokushoho/">特定商取引法に基づく表記</a>をご覧ください。</p>
<p class="muted">{h(PRIVACY_FORM)}</p>
</div>
<form class="f" id="f" novalidate enctype="multipart/form-data">
<input type="hidden" name="type" value="submission"><input type="hidden" name="opened" value="">
<div class="hp" aria-hidden="true"><label>空けておいてください<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
<label for="event_name">催しの名前</label><input type="text" id="event_name" name="event_name" maxlength="100" required>
<label for="date_from">開催日（始め）</label><input type="date" id="date_from" name="date_from" required>
<label for="date_to">開催日（終わり） <small>（1日だけなら空けてください）</small></label><input type="date" id="date_to" name="date_to">
<label for="time_text">時間 <small>（例：10:00〜15:00）</small></label><input type="text" id="time_text" name="time_text" maxlength="100">
<label for="venue">会場の名前</label><input type="text" id="venue" name="venue" maxlength="100" required>
<label for="city">市町</label><input type="text" id="city" name="city" maxlength="30" required placeholder="例：{h(AREAS[0][1] if AREAS else '')}">
<label for="address">住所 <small>（あれば）</small></label><input type="text" id="address" name="address" maxlength="200">
<label for="fee">料金 <small>（例：無料／大人500円）</small></label><input type="text" id="fee" name="fee" maxlength="100">
<div class="flyer"><input type="file" id="flyer" name="flyer" accept="image/jpeg,image/png,image/webp,application/pdf"><label for="flyer" class="filebtn"><span class="ic" aria-hidden="true">📎</span><span>チラシ・画像を添付する<small>あれば。画像（JPEG・PNG・WebP）か PDF、5MB まで。チラシがあると内容を早く確かめられます</small></span></label>
<div class="picked" id="flyer-picked" hidden><span id="flyer-thumb"></span><span class="nm" id="flyer-name"></span><button type="button" class="clear" id="flyer-clear">取り消す</button></div></div>
<script>(() => {{
  const i = document.getElementById("flyer"), box = document.getElementById("flyer-picked"),
    th = document.getElementById("flyer-thumb"), nm = document.getElementById("flyer-name");
  let url = "";
  const show = () => {{
    if (url) URL.revokeObjectURL(url), url = "";
    const f = i.files && i.files[0];
    box.hidden = !f; th.textContent = "";
    if (!f) return;
    nm.textContent = `${{f.name}}（${{f.size < 1048576 ? Math.ceil(f.size / 1024) + "KB" : (f.size / 1048576).toFixed(1) + "MB"}}）${{f.size > 5242880 ? " ※5MB を超えています" : ""}}`;
    if (f.type.startsWith("image/")) {{ const im = document.createElement("img"); url = URL.createObjectURL(f); im.src = url; im.alt = ""; th.append(im); }}
    else {{ const d = document.createElement("span"); d.className = "pdf"; d.textContent = "PDF"; th.append(d); }}
  }};
  i.addEventListener("change", show);
  document.getElementById("flyer-clear").addEventListener("click", () => {{ i.value = ""; show(); }});
}})();</script>
<label for="body">催しの内容 <small>（300字まで）</small></label><textarea id="body" name="body" maxlength="300" required></textarea>
<label for="target">対象・事前申し込み・締め切り <small>（あれば）</small></label><input type="text" id="target" name="target" maxlength="300">
<label for="organizer">主催者</label><input type="text" id="organizer" name="organizer" maxlength="100" required>
<label for="official_url">公式の URL または SNS <small>（ここを出典にします）</small></label><input type="url" id="official_url" name="official_url" maxlength="300" required placeholder="https://">
<label for="wish_from">掲載したい期間 <small>（あれば。最長30日）</small></label><input type="date" id="wish_from" name="wish_from"> 〜 <input type="date" id="wish_to" name="wish_to">
<label for="contact_name">ご担当者のお名前 <small>（公開しません）</small></label><input type="text" id="contact_name" name="contact_name" maxlength="100" required autocomplete="name">
<label for="contact_email">ご担当者のメールアドレス <small>（公開しません）</small></label><input type="email" id="contact_email" name="contact_email" maxlength="200" required autocomplete="email">
<label class="check"><input type="checkbox" name="agree" value="1" required>公式の案内で確かめてから掲載すること、上の個人情報の扱いに同意します</label>
<label class="check"><input type="checkbox" name="agree_flyer" value="1" required>提供した画像・チラシを、掲載・投稿に使ってよいことに同意します</label>
{_form_script("submission")}
"""
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title, "url": url}, ensure_ascii=False)
    return _shell(title, desc, url, ld, main, "../")


# ---- 特定商取引法に基づく表記（2026-10-20 代表。事業者の情報はふくいエキマエの表記と同じ） ----
TOKUSHOHO_DIR = ROOT / "docs" / "tokushoho"
TOKUSHOHO_MAIL = "contact@fukui-fukui.com"   # 2026-10-20 代表がさくらで作った連絡先（代表の Gmail に転送）


def render_tokushoho(today: date) -> str:
    from html import escape as h
    url = f"{SITE}/tokushoho/"
    title = f"特定商取引法に基づく表記｜{SITE_NAME}"
    desc = f"{SITE_NAME}のイベント掲載（有料）についての、特定商取引法に基づく表記です。"
    rows = [
        ("販売事業者", "ふくふくプロジェクト"),
        ("運営責任者", "請求があった場合には遅滞なく開示します"),
        ("所在地", "請求があった場合には遅滞なく開示します"),
        ("電話番号", "請求があった場合には遅滞なく開示します"),
        ("メールアドレス", TOKUSHOHO_MAIL),
        ("販売価格", "イベント掲載 1件 5,500円（税込）"),
        ("提供する内容", PAID_OFFER),
        ("商品代金以外の必要料金", "なし（インターネット接続にかかる通信料はお客様のご負担です）"),
        ("掲載の可否", "お申し込みの内容は、主催者などの公式の案内で確かめてから掲載します。"
                       + ("掲載できない場合は、仮押さえを取り消してご連絡します" if _uses("仮押さえ") else "掲載できない場合は、お支払いの前にご連絡します")),
        ("支払方法", "クレジットカード（Stripe による決済）"),
        ("支払時期", "お申し込みの際に、カードで 5,500円（税込）を仮押さえ（与信）します。掲載が決まった時点で確定し、"
                    "掲載できない場合は取り消します（料金は請求されません）。仮押さえの期限（7日）までに掲載を決められない場合も取り消します"
                    if _uses("仮押さえ") else "掲載のご案内（お支払いのリンク）をお送りしてから7日以内に、1回でお支払いください"),
        ("サービスの提供時期", "掲載が決まった日（確定した日）から3日以内に掲載を始めます" if _uses("仮押さえ")
                              else "お支払いを確かめてから3日以内に掲載を始めます"),
        ("返金について", "サービスの性質上、お支払い済みの料金の返金はいたしません。ただし、当方の責による不具合で掲載できなかった場合はこの限りではありません。"
                       "催しの中止・延期など事情がある場合は、お問い合わせフォームからご相談ください"),
        ("動作環境", "最新版の主要なブラウザ（Safari・Chrome・Edge など）"),
    ]
    dl = "".join(f"<tr><th>{h(k)}</th><td>{h(v)}</td></tr>" for k, v in rows)
    main = f"""<h1>特定商取引法に基づく表記</h1>
<div class="lead"><p>{h(SITE_NAME)}のイベント掲載（有料）についての表記です。掲載のお申し込みは、主催者の方からのみ受け付けます。{'<a href="../submit/">お申し込みはこちら</a>' if _uses("掲載申し込み") else ""}</p></div>
<table class="toku">{dl}</table>
<p><a href="../contact/">お問い合わせ</a> ・ <a href="../about/">運営者情報・編集方針・プライバシー</a></p>
"""
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title, "url": url}, ensure_ascii=False)
    return _shell(title, desc, url, ld, main, "../")


def write_months(data: dict, today: date) -> list[str]:
    # 前に作った月（docs/month/ にあるもの）は、過ぎても作り直して残す。消さない
    made = {d.name for d in MONTH_DIR.iterdir() if d.is_dir()} if MONTH_DIR.exists() else set()
    pages = month_pages(data, today, keep=made)
    keys = list(pages)
    for k, b in pages.items():
        (MONTH_DIR / k).mkdir(parents=True, exist_ok=True)
        (MONTH_DIR / k / "index.html").write_text(render_month(k, b, keys, today), encoding="utf-8")
    return keys


def render_404(months: list[str], today: date) -> str:
    """見つからないページ。消えた月のページなどから来た人を、トップと月のページへ案内する（2026-10-20）。"""
    ym = f"{today.year}-{today.month:02d}"
    near = [k for k in months if k >= ym][:2] or months[-2:]
    links = "".join(f'<li><a href="/month/{k}/">{_month_label(k)}の{KEN}のイベント</a></li>' for k in near)
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ページが見つかりません｜{SITE_NAME}</title>
<meta name="robots" content="noindex">
<link rel="icon" href="/favicon.ico" sizes="any">
<style>
body {{ margin: 0; background: #f5f1e8; color: #22302a; font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif; line-height: 1.8; overflow-wrap: anywhere; }}
main {{ max-width: 640px; margin: 0 auto; padding: 48px 16px; }}
h1 {{ font-size: 1.3rem; }}
a {{ color: #1f7a57; font-weight: 700; }}
@media (prefers-color-scheme: dark) {{ body {{ background: #141815; color: #e8eee9; }} a {{ color: #4cc292; }} }}
</style>
</head>
<body>
<main>
<h1>ページが見つかりませんでした</h1>
<p>URL が変わったか、ページがなくなった可能性があります。</p>
<ul>
<li><a href="/">{SITE_NAME}のトップ（{KEN}の今週末のイベント・新しいお店）</a></li>
{links}
</ul>
</main>
</body>
</html>
"""


def write_static(data: dict, today: date) -> None:
    months = write_months(data, today)
    (ROOT / "docs" / "404.html").write_text(render_404(months, today), encoding="utf-8")
    WEEKEND_DIR.mkdir(parents=True, exist_ok=True)
    (WEEKEND_DIR / "index.html").write_text(render_weekend(data, today), encoding="utf-8")
    SPOT_DIR.mkdir(parents=True, exist_ok=True)
    (SPOT_DIR / "index.html").write_text(render_spot(data, today), encoding="utf-8")
    areas = write_areas(data, today)
    if _uses("問い合わせ"):
        CONTACT_DIR.mkdir(parents=True, exist_ok=True)
        (CONTACT_DIR / "index.html").write_text(render_contact(today), encoding="utf-8")
    if _uses("特商法"):
        TOKUSHOHO_DIR.mkdir(parents=True, exist_ok=True)
        (TOKUSHOHO_DIR / "index.html").write_text(render_tokushoho(today), encoding="utf-8")
    if _uses("掲載申し込み"):
        SUBMIT_DIR.mkdir(parents=True, exist_ok=True)
        (SUBMIT_DIR / "index.html").write_text(render_submit(today), encoding="utf-8")
    html_text = INDEX.read_text(encoding="utf-8")
    a, b = html_text.find(MARK_START), html_text.find(MARK_END)
    if a < 0 or b < 0:
        print("::warning::index.html に prerender の目印がありません。静的な中身は書きません。")
    else:
        html_text = html_text[:a] + prerender(data, today) + html_text[b + len(MARK_END):]
    ma, mb = html_text.find(MONTHS_MARK[0]), html_text.find(MONTHS_MARK[1])
    if ma >= 0 and mb >= 0:
        links = ('<a href="./weekend/">今週末のイベント</a><br><a href="./spot/">新しいお店</a><br>'
                 + ("市町別：" + " ・ ".join(f'<a href="./area/{quote(a)}/">{a}</a>' for a in areas) + "<br>" if areas else "")) + "".join(f'<a href="./month/{k}/">{_month_label(k)}のイベント</a><br>' for k in months)
        html_text = html_text[:ma] + MONTHS_MARK[0] + links + html_text[mb:]
    INDEX.write_text(html_text, encoding="utf-8")
    lastmod = data.get("updated") or today.isoformat()
    urls = [(f"{SITE}/", lastmod, "daily"), (f"{SITE}/weekend/", today.isoformat(), "daily"),
            (f"{SITE}/spot/", lastmod, "daily"),
            *([(f"{SITE}/contact/", "2026-10-20", "yearly")] if _uses("問い合わせ") else []),
            *([(f"{SITE}/submit/", "2026-10-20", "yearly")] if _uses("掲載申し込み") else []),
            *[(f"{SITE}/area/{quote(a)}/", lastmod, "daily") for a in areas],
            (f"{SITE}/about/", "2026-10-04", "monthly")]
    urls += [(f"{SITE}/month/{k}/", lastmod, "daily") for k in months]
    SITEMAP.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{m}</lastmod><changefreq>{c}</changefreq></url>\n" for u, m, c in urls)
        + "</urlset>\n", encoding="utf-8")


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
        # 日本時間の今日で、終わった催しを外す
        from datetime import datetime, timedelta, timezone
        write_static(data, datetime.now(timezone(timedelta(hours=9))).date())
        print("→ docs/index.html（静的な中身）・docs/month/（月別ページ）・docs/sitemap.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
