"""Google アナリティクスと Search Console の数字を読んで、要点を insights/アクセス/ に残す

2026-10-13 代表（統括経由）「読めるようにして。どういう仕組みだと読める？」
読むだけのサービスアカウントを、代表が GA の各プロパティ（閲覧者）と Search Console の各サイトに足す。
鍵（JSON）は GitHub の Secrets「GA_SA_KEY」にだけ置く。

- GA：サービスアカウントが見られるプロパティを全部読む（ふくいおでかけ・いしかわおでかけ・ふくいエキマエなど）。
  プロパティ番号を書いておく必要はない（Analytics Admin API の一覧から取る）
- Search Console：サービスアカウントが足されたサイトを全部読む（検索語・よく出たページ・サイトマップ）
- 書き出し：insights/アクセス/最新.md と 最新.json。月曜は日付のファイルも残す

環境変数:
  GA_SA_KEY … サービスアカウントの鍵（JSON の中身）
  OUT_DIR   … 書き出し先（既定 insights/アクセス）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
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
       並べる: str | None = None) -> list[dict]:
    body = {
        "dateRanges": [{"startDate": 期間[0], "endDate": 期間[1]}],
        "dimensions": [{"name": d} for d in 次元],
        "metrics": [{"name": m} for m in 指標],
        "limit": 件,
    }
    if 並べる:
        body["orderBys"] = [{"metric": {"metricName": 並べる}, "desc": True}]
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
    }


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
            sm = よ.get(f"{GSC}/sites/{enc}/sitemaps").get("sitemap", [])
            x["サイトマップ"] = [{"path": m.get("path"), "最後に読まれた日": m.get("lastDownloaded"),
                              "エラー": int(m.get("errors", 0)), "警告": int(m.get("warnings", 0))} for m in sm]
        except requests.HTTPError as e:
            x["エラー"] = f"読めませんでした（{e.response.status_code}）"
        出.append(x)
    return 出


def _増減(今: int, 前: int) -> str:
    if not 前:
        return ""
    return f"（前の7日比 {(今 - 前) / 前 * 100:+.0f}%）"


def まとめる(結果: dict) -> str:
    行 = [f"# アクセスの要点（{結果['作った日']}）", "",
          "GA は昨日までの7日間。Search Console は3日前までの28日間（数字が2〜3日遅れるため）。", ""]
    for g in 結果["GA"]:
        行.append(f"## {g['名前']}（{', '.join(g['計測ID']) or g['property']}）")
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
        for m in s.get("サイトマップ", []):
            行.append(f"- サイトマップ {m['path']}：エラー {m['エラー']}・警告 {m['警告']}（最後に読まれた日 {m['最後に読まれた日']}）")
        行.append("")
    return "\n".join(行).rstrip() + "\n"


def main() -> None:
    key = os.environ.get("GA_SA_KEY", "").strip()
    if not key:
        print("::warning::GA_SA_KEY が未設定です。何もしません。")
        return
    よ = 読み手(json.loads(key))
    今日 = datetime.now(JST).date()
    結果 = {"作った日": 今日.isoformat(), "GA": [], "SC": []}
    try:
        props = プロパティ一覧(よ)
    except requests.HTTPError as e:
        print(f"::error::GA のプロパティ一覧を読めません（{e.response.status_code}）。"
              "Analytics Admin API が有効か、サービスアカウントが閲覧者に入っているかを確かめてください。")
        sys.exit(1)
    for p in props:
        g = {**p, "計測ID": 計測ID(よ, p["property"])}
        try:
            g.update(GAを読む(よ, p["property"]))
        except requests.HTTPError as e:
            g["エラー"] = f"読めませんでした（{e.response.status_code}。Analytics Data API が有効か確かめてください）"
        結果["GA"].append(g)
    結果["SC"] = SCを読む(よ)

    out = Path(os.environ.get("OUT_DIR", "insights/アクセス"))
    out.mkdir(parents=True, exist_ok=True)
    md = まとめる(結果)
    (out / "最新.md").write_text(md, encoding="utf-8")
    (out / "最新.json").write_text(json.dumps(結果, ensure_ascii=False, indent=1), encoding="utf-8")
    if 今日.weekday() == 0:
        (out / f"{今日.isoformat()}.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
