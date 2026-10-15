"""Google アナリティクスと Search Console の数字を読んで、要点を insights/アクセス/ に残す

2026-10-13 代表（統括経由）「読めるようにして。どういう仕組みだと読める？」
読むだけのサービスアカウントを、代表が GA の各プロパティ（閲覧者）と Search Console の各サイトに足す。
鍵（JSON）は GitHub の Secrets「GA_SA_KEY」にだけ置く。

- GA：サービスアカウントが見られるプロパティを全部読む（ふくいおでかけ・いしかわおでかけ・ふくいエキマエなど）。
  プロパティ番号を書いておく必要はない（Analytics Admin API の一覧から取る）
- Search Console：サービスアカウントが足されたサイトを全部読む（検索語・よく出たページ・サイトマップ）
- 書き出し：insights/アクセス/最新.md と 最新.json。月曜は日付のファイルも残す

- Cloudflare Web Analytics（2026-10-13 代表「1,2、3 進めて」）：Account Analytics: Read だけの API トークンで、
  サイト（ホスト）ごとの閲覧数・訪問・よく見られたページ・参照元を読む

環境変数:
  GA_SA_KEY     … サービスアカウントの鍵（JSON の中身）。無ければ GA・Search Console は読まない
  CF_API_TOKEN  … Cloudflare の API トークン（Account Analytics: Read）。無ければ Cloudflare は読まない
  CF_ACCOUNT_ID … Cloudflare のアカウント ID
  OUT_DIR   … 書き出し先（既定 insights/アクセス）
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2 import service_account

JST = ZoneInfo("Asia/Tokyo")
SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]
ADMIN = "https://analyticsadmin.googleapis.com/v1beta"
DATA = "https://analyticsdata.googleapis.com/v1beta"
GSC = "https://www.googleapis.com/webmasters/v3"
GSC_Q = "https://searchconsole.googleapis.com/webmasters/v3"


class 読み手:
    def __init__(self, key: dict):
        self.cred = service_account.Credentials.from_service_account_info(key, scopes=SCOPES)
        self.s = requests.Session()

    def _h(self) -> dict:
        if not self.cred.valid:
            self.cred.refresh(Request())
        return {"Authorization": f"Bearer {self.cred.token}"}

    def get(self, url: str, **params) -> dict:
        r = self.s.get(url, headers=self._h(), params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    def post(self, url: str, body: dict) -> dict:
        r = self.s.post(url, headers=self._h(), json=body, timeout=60)
        r.raise_for_status()
        return r.json()


def プロパティ一覧(よ: 読み手) -> list[dict]:
    出, token = [], None
    while True:
        d = よ.get(f"{ADMIN}/accountSummaries", pageSize=200, **({"pageToken": token} if token else {}))
        for a in d.get("accountSummaries", []):
            for p in a.get("propertySummaries", []):
                出.append({"property": p["property"], "名前": p.get("displayName", "")})
        token = d.get("nextPageToken")
        if not token:
            return 出


def 計測ID(よ: 読み手, prop: str) -> list[str]:
    try:
        d = よ.get(f"{ADMIN}/{prop}/dataStreams")
    except requests.HTTPError:
        return []
    return [s.get("webStreamData", {}).get("measurementId", "") for s in d.get("dataStreams", [])
            if s.get("webStreamData")]


def _表(よ: 読み手, prop: str, 期間: tuple[str, str], 次元: list[str], 指標: list[str], 件: int = 10,
       並べる: str | None = None, イベント: str | None = None) -> list[dict]:
    body = {
        "dateRanges": [{"startDate": 期間[0], "endDate": 期間[1]}],
        "dimensions": [{"name": d} for d in 次元],
        "metrics": [{"name": m} for m in 指標],
        "limit": 件,
    }
    if 並べる:
        body["orderBys"] = [{"metric": {"metricName": 並べる}, "desc": True}]
    if イベント:
        body["dimensionFilter"] = {"filter": {"fieldName": "eventName", "stringFilter": {"value": イベント}}}
    d = よ.post(f"{DATA}/{prop}:runReport", body)
    行 = []
    for r in d.get("rows", []):
        x = {n: v["value"] for n, v in zip(次元, r.get("dimensionValues", []))}
        x.update({n: _数(v["value"]) for n, v in zip(指標, r.get("metricValues", []))})
        行.append(x)
    return 行


def _数(v: str):
    try:
        f = float(v)
        return int(f) if f.is_integer() else round(f, 2)
    except ValueError:
        return v


def GAを読む(よ: 読み手, prop: str) -> dict:
    今週 = ("7daysAgo", "yesterday")
    前週 = ("14daysAgo", "8daysAgo")
    合計 = ["screenPageViews", "activeUsers", "sessions"]
    t = _表(よ, prop, 今週, [], 合計, 1)
    p = _表(よ, prop, 前週, [], 合計, 1)
    return {
        "直近7日": t[0] if t else {},
        "その前の7日": p[0] if p else {},
        "日ごと": _表(よ, prop, 今週, ["date"], ["screenPageViews", "activeUsers"], 7),
        "どこから": _表(よ, prop, 今週, ["sessionDefaultChannelGroup"], ["sessions"], 10, "sessions"),
        "参照元": _表(よ, prop, 今週, ["sessionSource"], ["sessions"], 10, "sessions"),
        "よく見られたページ": _表(よ, prop, 今週, ["pagePath"], ["screenPageViews"], 10, "screenPageViews"),
        "よく見られたお店": お店を読む(よ, prop, 今週),
        "投稿ごと": 投稿ごとを読む(よ, prop, 今週),
    }


def 投稿ごとを読む(よ: 読み手, prop: str, 期間: tuple[str, str]) -> list[dict]:
    """Threads の投稿から来た訪問を、投稿の id（utm_content）ごとに数える（2026-10-13 代表「つける」）。"""
    try:
        行 = _表(よ, prop, 期間, ["sessionManualAdContent", "sessionCampaignName"], ["sessions"], 15, "sessions")
    except requests.HTTPError:
        return []
    return [{"投稿": r["sessionManualAdContent"], "キャンペーン": r["sessionCampaignName"], "訪問": r["sessions"]}
            for r in 行 if r.get("sessionManualAdContent") not in ("", "(not set)")]


def お店を読む(よ: 読み手, prop: str, 期間: tuple[str, str]) -> list[dict]:
    """エキマエの「shop_view」イベントを店名ごとに数える（2026-10-13 代表が GA に shop_name・shop_zone・shop_genre を登録）。
    そのカスタムディメンションが無いプロパティ（おでかけなど）では空にする。"""
    try:
        行 = _表(よ, prop, 期間, ["customEvent:shop_name", "customEvent:shop_zone", "customEvent:shop_genre"],
                 ["eventCount"], 20, "eventCount", イベント="shop_view")
    except requests.HTTPError:
        return []
    return [{"店名": r["customEvent:shop_name"], "エリア": r["customEvent:shop_zone"],
             "ジャンル": r["customEvent:shop_genre"], "回数": r["eventCount"]}
            for r in 行 if r.get("customEvent:shop_name") not in ("", "(not set)")]


サイトの名前 = ["odekake.fukui-fukui.com", "ishikawa-odekake.fukui-fukui.com", "gifu-aichi-odekake.fukui-fukui.com", "ekimae.fukui-fukui.com"]


def SCを読む(よ: 読み手) -> list[dict]:
    try:
        sites = よ.get(f"{GSC}/sites").get("siteEntry", [])
    except requests.HTTPError as e:
        return [{"エラー": f"Search Console を読めません（{e.response.status_code}）"}]
    今日 = datetime.now(JST).date()
    # Search Console の数字は 2〜3 日遅れるので、3 日前までの 28 日
    終 = (今日 - timedelta(days=3)).isoformat()
    始 = (今日 - timedelta(days=30)).isoformat()
    出 = []
    for s in sites:
        url = s["siteUrl"]
        enc = requests.utils.quote(url, safe="")
        x = {"サイト": url, "権限": s.get("permissionLevel"), "期間": f"{始}〜{終}"}
        try:
            for 次元, 名 in (("query", "検索語"), ("page", "検索に出たページ")):
                d = よ.post(f"{GSC_Q}/sites/{enc}/searchAnalytics/query",
                            {"startDate": 始, "endDate": 終, "dimensions": [次元], "rowLimit": 20})
                x[名] = [{"語" if 次元 == "query" else "ページ": r["keys"][0], "クリック": r["clicks"],
                          "表示": r["impressions"], "順位": round(r["position"], 1)} for r in d.get("rows", [])]
            d = よ.post(f"{GSC_Q}/sites/{enc}/searchAnalytics/query", {"startDate": 始, "endDate": 終})
            r = (d.get("rows") or [{}])[0]
            x["合計"] = {"クリック": r.get("clicks", 0), "表示": r.get("impressions", 0)}
            # ドメインのプロパティ（sc-domain:）は、サイトごと（おでかけ福井・石川・エキマエ）にも分けて見る
            # （2026-10-13 エキマエ開発「ekimae.fukui-fukui.com のページに絞って」）
            if url.startswith("sc-domain:"):
                x["サイトごと"] = []
                for host in サイトの名前:
                    f = {"dimensionFilterGroups": [{"filters": [
                        {"dimension": "page", "operator": "contains", "expression": f"://{host}/"}]}]}
                    合 = (よ.post(f"{GSC_Q}/sites/{enc}/searchAnalytics/query",
                                 {"startDate": 始, "endDate": 終, **f}).get("rows") or [{}])[0]
                    語 = よ.post(f"{GSC_Q}/sites/{enc}/searchAnalytics/query",
                                {"startDate": 始, "endDate": 終, "dimensions": ["query"], "rowLimit": 10, **f}).get("rows", [])
                    x["サイトごと"].append({"サイト": host, "クリック": 合.get("clicks", 0), "表示": 合.get("impressions", 0),
                                         "検索語": [{"語": r["keys"][0], "クリック": r["clicks"], "表示": r["impressions"],
                                                   "順位": round(r["position"], 1)} for r in 語]})
            sm = よ.get(f"{GSC}/sites/{enc}/sitemaps").get("sitemap", [])
            x["サイトマップ"] = [{"path": m.get("path"), "最後に読まれた日": m.get("lastDownloaded"),
                              "エラー": int(m.get("errors", 0)), "警告": int(m.get("warnings", 0))} for m in sm]
        except requests.HTTPError as e:
            x["エラー"] = f"読めませんでした（{e.response.status_code}）"
        出.append(x)
    return 出


CF_GQL = "https://api.cloudflare.com/client/v4/graphql"
CF_Q = """query($a: String!, $s: Date!, $e: Date!) { viewer { accounts(filter: {accountTag: $a}) {
  host: rumPageloadEventsAdaptiveGroups(limit: 50, filter: {date_geq: $s, date_leq: $e}, orderBy: [count_DESC]) {
    count sum { visits } dimensions { requestHost } }
  path: rumPageloadEventsAdaptiveGroups(limit: 60, filter: {date_geq: $s, date_leq: $e}, orderBy: [count_DESC]) {
    count dimensions { requestHost requestPath } }
  ref: rumPageloadEventsAdaptiveGroups(limit: 60, filter: {date_geq: $s, date_leq: $e}, orderBy: [count_DESC]) {
    count dimensions { requestHost refererHost } }
} } }"""


def CFを読む(token: str, account: str) -> list[dict]:
    """昨日までの7日間の、ホストごとの閲覧数・訪問・ページ・参照元。"""
    # アカウント ID は32文字の英数字。違う形（トークンを入れ違えたなど）なら、中身は出さずに止める
    # （2026-10-13 1回目、Cloudflare のエラー文に入れた値がそのまま返り、書き出しにトークンが載りかけた）
    if not re.fullmatch(r"[0-9a-f]{32}", account):
        return [{"エラー": "Secrets の CF_ACCOUNT_ID の形が違います（32文字の英数字のはず）。"
                         "CF_API_TOKEN と CF_ACCOUNT_ID を入れ違えていないか確かめてください"}]
    今日 = datetime.now(JST).date()
    v = {"a": account, "s": (今日 - timedelta(days=7)).isoformat(), "e": (今日 - timedelta(days=1)).isoformat()}
    try:
        r = requests.post(CF_GQL, headers={"Authorization": f"Bearer {token}"},
                          json={"query": CF_Q, "variables": v}, timeout=60)
        r.raise_for_status()
        d = r.json()
    except requests.RequestException as e:
        code = getattr(getattr(e, "response", None), "status_code", None) or type(e).__name__
        # トークンの中身は出さず、形だけ伝える（空白・改行・日本語などが混ざると送る前に失敗する）
        形 = "英数字と - _ だけ" if re.fullmatch(r"[A-Za-z0-9_\-]+", token) else "英数字以外（空白・改行・記号など）が混ざっている"
        return [{"エラー": f"Cloudflare を読めません（{code}）。トークンは {len(token)} 文字・{形}。"
                         "トークンの権限（Account Analytics: Read）と、貼った値を確かめてください"}]
    if d.get("errors"):
        return [{"エラー": f"Cloudflare を読めません（エラー {len(d['errors'])} 件）。"
                         "トークンの権限（Account Analytics: Read）とアカウント ID を確かめてください"}]
    acc = ((d.get("data") or {}).get("viewer") or {}).get("accounts") or [{}]
    acc = acc[0] if acc else {}
    出 = []
    for h in acc.get("host") or []:
        host = h["dimensions"]["requestHost"]
        出.append({
            "サイト": host, "期間": f"{v['s']}〜{v['e']}",
            "閲覧数": h["count"], "訪問": (h.get("sum") or {}).get("visits", 0),
            "よく見られたページ": [{"ページ": x["dimensions"]["requestPath"], "閲覧数": x["count"]}
                             for x in acc.get("path") or [] if x["dimensions"]["requestHost"] == host][:10],
            "参照元": [{"参照元": x["dimensions"]["refererHost"] or "（直接・不明）", "閲覧数": x["count"]}
                    for x in acc.get("ref") or [] if x["dimensions"]["requestHost"] == host][:10],
        })
    return 出


def _増減(今: int, 前: int) -> str:
    if not 前:
        return ""
    return f"（前の7日比 {(今 - 前) / 前 * 100:+.0f}%）"


def まとめる(結果: dict) -> str:
    行 = [f"# アクセスの要点（{結果['作った日']}）", "",
          "GA は昨日までの7日間。Search Console は3日前までの28日間（数字が2〜3日遅れるため）。", ""]
    for g in 結果["GA"]:
        印 = ", ".join(g["計測ID"]) or g["property"]
        行.append(f"## {g['名前']}" + (f"（{印}）" if 印 else ""))
        if "エラー" in g:
            行 += [f"- {g['エラー']}", ""]
            continue
        t, p = g["直近7日"], g["その前の7日"]
        行.append(f"- 閲覧数 {t.get('screenPageViews', 0):,}{_増減(t.get('screenPageViews', 0), p.get('screenPageViews', 0))}"
                  f"／利用者 {t.get('activeUsers', 0):,}／訪問 {t.get('sessions', 0):,}")
        if g["どこから"]:
            行.append("- どこから：" + "、".join(f"{r['sessionDefaultChannelGroup']} {r['sessions']}" for r in g["どこから"]))
        if g["参照元"]:
            行.append("- 参照元：" + "、".join(f"{r['sessionSource']} {r['sessions']}" for r in g["参照元"]))
        if g["よく見られたページ"]:
            行.append("- よく見られたページ：")
            行 += [f"  - {r['pagePath']} … {r['screenPageViews']}" for r in g["よく見られたページ"]]
        if g.get("投稿ごと"):
            行.append("- Threads の投稿ごとの訪問（UTM）：" + "、".join(f"{r['投稿']} {r['訪問']}" for r in g["投稿ごと"]))
        if g.get("よく見られたお店"):
            行.append("- よく見られたお店（shop_view の回数）：")
            行 += [f"  - {r['店名']}（{r['エリア']}・{r['ジャンル']}） … {r['回数']}" for r in g["よく見られたお店"]]
        行.append("")
    for s in 結果["SC"]:
        行.append(f"## Search Console：{s.get('サイト', '')}")
        if "エラー" in s:
            行 += [f"- {s['エラー']}", ""]
            continue
        c = s.get("合計", {})
        行.append(f"- {s['期間']}：クリック {c.get('クリック', 0):,}／検索結果に出た回数 {c.get('表示', 0):,}")
        if s.get("検索語"):
            行.append("- 検索語（上位）：")
            行 += [f"  - {r['語']} … クリック {r['クリック']}・表示 {r['表示']}・平均順位 {r['順位']}" for r in s["検索語"][:15]]
        for h in s.get("サイトごと", []):
            行.append(f"- {h['サイト']}：クリック {h['クリック']:,}／検索結果に出た回数 {h['表示']:,}")
            行 += [f"  - {r['語']} … クリック {r['クリック']}・表示 {r['表示']}・平均順位 {r['順位']}" for r in h["検索語"][:5]]
        for m in s.get("サイトマップ", []):
            行.append(f"- サイトマップ {m['path']}：エラー {m['エラー']}・警告 {m['警告']}（最後に読まれた日 {m['最後に読まれた日']}）")
        行.append("")
    for c in 結果.get("CF", []):
        行.append(f"## Cloudflare：{c.get('サイト', '')}")
        if "エラー" in c:
            行 += [f"- {c['エラー']}", ""]
            continue
        行.append(f"- {c['期間']}：閲覧数 {c['閲覧数']:,}／訪問 {c['訪問']:,}")
        if c["参照元"]:
            行.append("- 参照元：" + "、".join(f"{r['参照元']} {r['閲覧数']}" for r in c["参照元"]))
        if c["よく見られたページ"]:
            行.append("- よく見られたページ：")
            行 += [f"  - {r['ページ']} … {r['閲覧数']}" for r in c["よく見られたページ"]]
        行.append("")
    return "\n".join(行).rstrip() + "\n"


def main() -> None:
    key = os.environ.get("GA_SA_KEY", "").strip()
    cf_token = os.environ.get("CF_API_TOKEN", "").strip()
    cf_account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    if not key and not (cf_token and cf_account):
        print("::warning::GA_SA_KEY も CF_API_TOKEN・CF_ACCOUNT_ID も未設定です。何もしません。")
        return
    今日 = datetime.now(JST).date()
    結果 = {"作った日": 今日.isoformat(), "GA": [], "SC": [], "CF": []}
    よ = None
    if key:
        try:
            よ = 読み手(json.loads(key))
            よ._h()
        except (ValueError, GoogleAuthError) as e:
            # 鍵が壊れている・消された・別の鍵などで、Google にログインできないとき。Cloudflare は続けて読む
            print(f"::error::Google にログインできません（{type(e).__name__}）")
            結果["GA"].append({"名前": "Google アナリティクス・Search Console", "計測ID": [], "property": "",
                              "エラー": "Google にログインできません（鍵が正しくありません）。Google Cloud で新しい JSON の鍵を作り、"
                                       "Secrets の GA_SA_KEY を中身全部で入れ直してください"})
            よ = None
    if よ:
        try:
            props = プロパティ一覧(よ)
        except requests.HTTPError as e:
            props = []
            結果["GA"].append({"名前": "Google アナリティクス", "計測ID": [], "property": "",
                              "エラー": f"プロパティ一覧を読めません（{e.response.status_code}）。Analytics Admin API が有効か、"
                                       "サービスアカウントが閲覧者に入っているかを確かめてください"})
        for p in props:
            g = {**p, "計測ID": 計測ID(よ, p["property"])}
            try:
                g.update(GAを読む(よ, p["property"]))
            except requests.HTTPError as e:
                g["エラー"] = f"読めませんでした（{e.response.status_code}。Analytics Data API が有効か確かめてください）"
            結果["GA"].append(g)
        結果["SC"] = SCを読む(よ)
    if cf_token and cf_account:
        結果["CF"] = CFを読む(cf_token, cf_account)

    md_json = json.dumps(結果, ensure_ascii=False, indent=1)
    md = まとめる(結果)
    for 秘密 in (cf_token, cf_account, key):
        if 秘密 and len(秘密) >= 8:
            md, md_json = md.replace(秘密, "＊＊＊"), md_json.replace(秘密, "＊＊＊")
    out = Path(os.environ.get("OUT_DIR", "insights/アクセス"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "最新.md").write_text(md, encoding="utf-8")
    (out / "最新.json").write_text(md_json, encoding="utf-8")
    if 今日.weekday() == 0:
        (out / f"{今日.isoformat()}.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
