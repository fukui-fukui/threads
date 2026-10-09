"""福井版のリポジトリから、別の県のおでかけ（石川版など）のリポジトリ一式を作る。

    python scripts/地域の写し.py regions/ishikawa 出力先のフォルダ

regions/<県>/ に置いた region.json・巡回先.json・設定.json を使い、
プログラム（scripts・src・tests・ワークフロー）はそのまま、サイト（docs）は
福井版のページを元に、県名・サイト名・アカウント・地区だけを置きかえて写す。
福井版で直したことを石川版にも入れたいときは、これをもう一度走らせて差分を見る。

写さないもの：投稿の記録（posts・state・insights）、福井のネタ帳と集めたデータ、
regions フォルダ、福井だけの設定（CNAME・ふるさと納税のリンク）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 写さないもの（ROOT からの相対パス）
SKIP = {
    ".git", "regions", "posts", "state", "insights", "__pycache__",
    "neta/ネタ帳.md", "neta/巡回先.json", "neta/設定.json",
    "neta/ふるさと納税_リンク.jsonl", "neta/ふるさと納税_切り口リンク.jsonl",
    "docs/data.json", "docs/hotels.json", "docs/month", "docs/sitemap.xml", "docs/CNAME",
    "scripts/_アーカイブ", "scripts/地域の写し.py",
    # 予算の見張りは福井のリポジトリでまとめて行う（石川の分も足す）
    "予算.json", "scripts/予算.mjs", ".github/workflows/budget-check.yml",
}
SKIP_PREFIX = ("neta/_ネタ帳",)

# 福井版の値（region.json）。ページの中のこれを、写し先の値に置きかえる
福井 = json.loads((ROOT / "region.json").read_text(encoding="utf-8"))


class 合わない(Exception):
    """福井版のページの形が変わって、置きかえる場所が見つからない。"""


def 置く(文: str, 元: str, 先: str, 何回: int | None = None) -> str:
    n = 文.count(元)
    if n == 0 or (何回 is not None and n != 何回):
        raise 合わない(f"見つからない（{n} 回）: {元[:60]!r}")
    return 文.replace(元, 先)


def 正規(文: str, 形: str, 先: str, flags: int = re.S) -> str:
    新, n = re.subn(形, 先, 文, flags=flags)
    if n == 0:
        raise 合わない(f"見つからない: {形[:60]!r}")
    return 新


def 共通(文: str, 地: dict) -> str:
    """どのページにも出てくる、サイト・アカウントの置きかえ。"""
    文 = 文.replace(福井["サイトURL"].rstrip("/"), 地["サイトURL"].rstrip("/"))
    文 = 文.replace(f"@{福井['アカウント']}", f"@{地['アカウント']}")
    文 = 文.replace(福井["サイト名"], 地["サイト名"])
    # Google アナリティクス・Cloudflare は、写し先に ID が無ければタグごと外す
    if 地.get("GA"):
        文 = 文.replace(福井["GA"], 地["GA"])
    else:
        文 = re.sub(r"<!-- Google アナリティクス[^\n]*-->\n", "", 文)
        文 = re.sub(r'<script async src="https://www\.googletagmanager\.com/gtag/js\?id=[^"]+"></script>\n?', "", 文)
        文 = re.sub(r"<script>window\.dataLayer=[^<]*</script>\n?", "", 文)
    if 地.get("Cloudflare"):
        文 = 文.replace(福井["Cloudflare"], 地["Cloudflare"])
    else:
        文 = re.sub(r"<!-- Cloudflare Web Analytics[^\n]*?-->", "", 文)
        文 = re.sub(r"<script type='module' src='https://static\.cloudflareinsights\.com/beacon\.min\.js'[^>]*></script>\n?", "", 文)
        文 = re.sub(r'<script type="module" src="https://static\.cloudflareinsights\.com/beacon\.min\.js"[^>]*></script>\n?', "", 文)
        文 = re.sub(r"<!-- Cloudflare Web Analytics[^\n]*\n?", "", 文)
    return 文


def 地区の表(地: dict) -> dict[str, list[str]]:
    """サイトの絞り込みに使う「地区 → 市町」の表。地名の表に出てくる市町を、地区に振り分ける。"""
    区 = 地["地区"]
    名前たち = [*区["区切り"], 区["ほかは"]]
    表: dict[str, list[str]] = {}
    市町たち = []
    for _, 市町 in 地["地名"]:
        if 市町 not in 市町たち:
            市町たち.append(市町)
    # 並びは、ほかは（加賀など）→ 区切り（金沢・能登など）の順ではなく、地図の南から
    for 名 in 地.get("地区の並び", 名前たち):
        if 名 == 区["ほかは"]:
            表[名] = [c for c in 市町たち if not any(c in 区.get(k, []) for k in 区["区切り"])]
        else:
            表[名] = [c for c in 区.get(名, []) if c in 市町たち] or list(区.get(名, []))
    return 表


def トップ(文: str, 地: dict) -> str:
    県, 県名 = 地["県"], 地["県名"]
    文 = 共通(文, 地)
    # 検索エンジン向けの静的な中身と、月別ページへのリンクは、写し先で作り直す
    文 = 正規(文, r"<!--prerender:start-->.*?<!--prerender:end-->",
            "<!--prerender:start-->\n<div class=\"prerender\">\n</div>\n<!--prerender:end-->")
    文 = 正規(文, r"<!--months:start-->.*?<!--months:end-->", "<!--months:start--><!--months:end-->")
    # 地区の表（JavaScript）
    表 = 地区の表(地)
    行 = "\n".join(f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}," for k, v in 表.items())
    文 = 正規(文, r"  const AREAS = \{\n.*?\n  \};", f"  const AREAS = {{\n{行}\n  }};")
    ボタン = json.dumps([["", 県], *[[k, k] for k in 表]], ensure_ascii=False)
    文 = 置く(文, '[["", "福井県"], ["嶺北", "嶺北"], ["嶺南", "嶺南"]]', ボタン, 1)
    文 = 置く(文, '[...AREAS["嶺北"], ...AREAS["嶺南"]]', "Object.values(AREAS).flat()", 1)
    # 地域ボタンの数（県全体＋地区）に合わせて1段に並べる
    文 = 置く(文, ".seg { display: grid; grid-template-columns: repeat(3, 1fr);",
             f".seg {{ display: grid; grid-template-columns: repeat({len(表) + 1}, 1fr);", 1)
    # 宿を使わない県は「泊まる」のタブと楽天の表示を外す
    if not 地.get("使う", {}).get("宿", True):
        文 = 正規(文, r'\n    \["stay", "泊まる", "i-bed", "[^"]*"\],', "")
        文 = 置く(文, "  「泊まる」の宿の情報・写真は楽天トラベルのものです。宿へのリンクは楽天アフィリエイト（PR）です。<br>\n", "", 1)
        文 = 置く(文, '  <a href="https://webservice.rakuten.co.jp/" target="_blank" rel="noopener">Supported by Rakuten Developers</a><br>\n', "", 1)
    else:
        文 = 文.replace("福井に泊まる", f"{県名}に泊まる")
    # 残りの「福井」（見出し・説明文）を県名にする。福井県 → 石川県 を先に
    文 = 文.replace("福井県", 県).replace("福井", 県名)
    return 文


def 運営者情報(文: str, 地: dict) -> str:
    県, 県名 = 地["県"], 地["県名"]
    文 = 共通(文, 地)
    表示名 = 地.get("Threadsの表示名", 地["サイト名"])
    文 = 置く(文, "Threads「ふくふく | 福井おでかけ」", f"Threads「{表示名}」")
    # 姉妹サイトは福井のもの。写し先では「福井版」として案内する
    文 = 正規(文, r"<li>姉妹サイト：.*?</li>",
            f'<li>姉妹サイト：<a href="{福井["サイトURL"]}/">{福井["サイト名"]}</a>（福井県版）</li>')
    if not 地.get("使う", {}).get("宿", True):
        文 = 正規(文, r"<li>「泊まる」の宿の紹介は、楽天トラベル.*?</li>\n", "")
        文 = 置く(文, "<li>宿の情報・写真は楽天トラベルのものです。</li>\n", "", 1)
        文 = 置く(文, "<li>楽天トラベルのリンクを押すと、楽天のサイトで Cookie が使われることがあります。</li>\n", "", 1)
    計測 = [n for n, k in (("Cloudflare Web Analytics", "Cloudflare"), ("Google アナリティクス", "GA")) if 地.get(k)]
    if 計測:
        文 = 置く(文, "Cloudflare Web Analytics と Google アナリティクスを使っています", f"{' と '.join(計測)}を使っています", 1)
    else:
        文 = 正規(文, r"<li>訪問数やよく見られているページを把握するため、.*?</li>\n", "")
    if not 地.get("GA"):
        文 = 正規(文, r"<li>Google アナリティクスは Cookie を使い、.*?</li>\n", "")
    # 姉妹サイトの行を守ってから、残りの「福井」を置きかえる
    守る = re.search(r"<li>姉妹サイト：.*?</li>", 文, re.S).group(0)
    文 = 文.replace(守る, "\0姉妹\0")
    文 = 文.replace("福井県", 県).replace("福井", 県名)
    return 文.replace("\0姉妹\0", 守る)


def そのほかのページ(相対: str, 文: str, 地: dict, 新リポジトリ: str) -> str:
    if 相対 == "docs/robots.txt":
        return 共通(文, 地)
    if 相対 == "docs/odekake/index.html":
        return 共通(文, 地)
    if 相対 == "docs/yoyaku/app.js":
        return 置く(文, 'return "fukui-fukui/threads";', f'return "{新リポジトリ}";', 1)
    if 相対 == "docs/yoyaku/index.html":
        return 文.replace("例: 雨の降る福井の街並み", f"例: 雨の降る{地['県名']}の街並み")
    return 文


def ワークフロー(相対: str, 文: str, 地: dict) -> str | None:
    """写し先のワークフロー。None を返したものは写さない。"""
    使う = 地.get("使う", {})
    if 相対.endswith("rakuten-check.yml") and not 使う.get("宿", True):
        return None
    if 相対.endswith("threads-post.yml"):
        # 写し先は、リポジトリの変数 POST_ENABLED を true にするまで投稿しない（試運転のため）
        文 = 置く(文, "jobs:\n  post:\n    runs-on: ubuntu-latest\n",
                 "jobs:\n  post:\n    # 試運転のあいだは投稿しない。公開の日に、リポジトリの変数 POST_ENABLED を true にする\n"
                 "    if: ${{ vars.POST_ENABLED == 'true' }}\n    runs-on: ubuntu-latest\n", 1)
    if 相対.endswith("threads-compose.yml"):
        # 写し先には外部の cron（cron-job.org）がまだ無いので、GitHub の schedule で毎晩 20:00 JST に作る
        文 = 置く(文, "  repository_dispatch:\n    types: [threads-compose]\n",
                 "  repository_dispatch:\n    types: [threads-compose]\n"
                 "  # 外部 cron が無いあいだの起動（20:00 JST。少し遅れることがある）\n"
                 "  schedule:\n    - cron: \"0 11 * * *\"\n", 1)
    if 相対.endswith("threads-compose.yml") and not 使う.get("クーポン", True):
        文 = 正規(文, r"\n      # 楽天トラベルの40%OFF以上のクーポン.*?run: python \"scripts/クーポンの投稿.py\"\n", "\n")
    return 文


def 申し送り(地: dict) -> str:
    return (
        "# Claude への申し送り\n\n"
        f"このリポジトリは「{地['サイト名']}」（{地['県']}版のおでかけサイトと Threads @{地['アカウント']}）。\n"
        "福井版 fukui-fukui/threads の scripts/地域の写し.py で作った写しで、プログラムは福井版と同じ。\n"
        "県ごとに違うところは region.json・neta/巡回先.json・neta/設定.json だけに書く。\n"
        "プログラムを直すときは、福井版で直してから写し直す（ここだけで直すと、次に写したときに消える）。\n\n"
        "ふくふくプロジェクトの引き継ぎと、セッション間の連絡は、代表の Google ドライブ「AI会社」フォルダにまとめている。\n"
        "作業を始めたら、Google ドライブ連携でまず次を読むこと。\n\n"
        "1. AI会社/00_使い方（ルール。ファイルの直し方もここ）\n"
        f"2. AI会社/引き継ぎ/ の担当ファイル（このリポジトリなら {地['サイト名']}）\n"
        "3. AI会社/連絡/ の自分あてのもの\n\n"
        "作業の区切りでは、担当の引き継ぎファイルを最新にする（鍵・パスワードは書かない）。\n"
    )


def 写す(地のフォルダ: Path, 出力: Path) -> list[str]:
    地 = json.loads((地のフォルダ / "region.json").read_text(encoding="utf-8"))
    新リポジトリ = 地.get("リポジトリ", "fukui-fukui/odekake-" + 地のフォルダ.name)
    出力.mkdir(parents=True, exist_ok=True)
    書いた = []
    # git に入っているファイルだけを写す（手元だけの設定や作業中のファイルを持ち出さない）
    入っている = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    for 相対 in sorted(x.decode("utf-8") for x in 入っている.split(b"\0") if x):
        元 = ROOT / 相対
        if not 元.exists():
            continue
        if any(相対 == s or 相対.startswith(s + "/") for s in SKIP) or 相対.startswith(SKIP_PREFIX):
            continue
        if any(p == "__pycache__" for p in 元.parts):
            continue
        if 元.is_dir():
            continue
        先 = 出力 / 相対
        先.parent.mkdir(parents=True, exist_ok=True)
        if 相対 == "region.json":
            continue
        if 相対.startswith(".github/workflows/"):
            文 = ワークフロー(相対, 元.read_text(encoding="utf-8"), 地)
            if 文 is None:
                continue
            先.write_text(文, encoding="utf-8")
        elif 相対 == "CLAUDE.md":
            先.write_text(申し送り(地), encoding="utf-8")
        elif 相対 == "README.md":
            先.write_text(共通(元.read_text(encoding="utf-8"), 地), encoding="utf-8")
        elif 元.suffix in (".html", ".js", ".txt") and 相対.startswith("docs/"):
            文 = 元.read_text(encoding="utf-8")
            if 相対 == "docs/index.html":
                文 = トップ(文, 地)
            elif 相対 == "docs/about/index.html":
                文 = 運営者情報(文, 地)
            else:
                文 = そのほかのページ(相対, 文, 地, 新リポジトリ)
            先.write_text(文, encoding="utf-8")
        else:
            shutil.copy2(元, 先)
        書いた.append(相対)
    # 県ごとの設定
    shutil.copy2(地のフォルダ / "region.json", 出力 / "region.json")
    # 県ごとのアイコン・ロゴ（regions/<県>/docs/ に置いたもの）で、福井のものを置きかえる
    if (地のフォルダ / "docs").is_dir():
        for 元 in sorted((地のフォルダ / "docs").rglob("*")):
            if 元.is_file():
                相対 = "docs/" + 元.relative_to(地のフォルダ / "docs").as_posix()
                (出力 / 相対).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(元, 出力 / 相対)
                if 相対 not in 書いた:
                    書いた.append(相対)
        # ブラウザは前のアイコンを長く覚えているので、県のアイコンを使うページはアドレスに印を付けて読み直させる
        印 = "?v=" + 地のフォルダ.name
        for 名 in ("docs/index.html", "docs/about/index.html"):
            if (出力 / 名).exists():
                文 = (出力 / 名).read_text(encoding="utf-8")
                文 = re.sub(r'href="((?:\.\./)*(?:favicon\.ico|favicon-32\.png|icon-192\.png|apple-touch-icon\.png|logo\.jpg))"', rf'href="\1{印}"', 文)
                文 = re.sub(r'src="((?:\.\./)*logo\.jpg)"', rf'src="\1{印}"', 文)
                (出力 / 名).write_text(文, encoding="utf-8")
    (出力 / "neta").mkdir(exist_ok=True)
    for 名 in ("巡回先.json", "設定.json"):
        shutil.copy2(地のフォルダ / 名, 出力 / "neta" / 名)
    書いた += ["region.json", "neta/巡回先.json", "neta/設定.json"]
    # 宿を集める県には、楽天トラベルから宿のリストを作るワークフローを置く
    設定 = json.loads((地のフォルダ / "設定.json").read_text(encoding="utf-8"))
    if 設定.get("宿の集めかた"):
        shutil.copy2(ROOT / "regions" / "_共通" / "hotel-collect.yml", 出力 / ".github" / "workflows" / "hotel-collect.yml")
        書いた.append(".github/workflows/hotel-collect.yml")
    if 設定.get("ふるさと納税の集めかた"):
        shutil.copy2(ROOT / "regions" / "_共通" / "furusato-collect.yml", 出力 / ".github" / "workflows" / "furusato-collect.yml")
        書いた.append(".github/workflows/furusato-collect.yml")
    # 空のネタ帳・投稿の置き場（仕組みが最初の日に読めるように）
    ネタ帳 = 出力 / "neta" / "ネタ帳.md"
    if not ネタ帳.exists():
        ネタ帳.write_text(
            "# ネタ帳\n\n## 調べてほしいもの\n\n（店名だけ、うろ覚えでもここに書けば、翌朝の収集が調べて本体に入れます）\n\n"
            "## 使ってほしくないネタ\n\n（ここに書いたものは集めません）\n\n## 書き足す場所\n",
            encoding="utf-8",
        )
        書いた.append("neta/ネタ帳.md")
    (出力 / "posts").mkdir(exist_ok=True)
    (出力 / "posts" / "queue.jsonl").touch()
    # 投稿済みの記録は最初から置いておく（無いと初めての投稿の記録が残らず、二重投稿になりうる）
    (出力 / "state").mkdir(exist_ok=True)
    if not (出力 / "state" / "posted.json").exists():
        (出力 / "state" / "posted.json").write_text('{\n  "posted": {},\n  "version": 1\n}\n', encoding="utf-8")
    # 独自ドメインのときだけ CNAME を置く（github.io のあいだは置かない）
    host = re.sub(r"^https?://", "", 地["サイトURL"]).split("/")[0]
    if not host.endswith("github.io"):
        (出力 / "docs" / "CNAME").write_text(host + "\n", encoding="utf-8")
        書いた.append("docs/CNAME")
    return 書いた


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    書いた = 写す(ROOT / argv[0] if not Path(argv[0]).is_absolute() else Path(argv[0]), Path(argv[1]))
    print(f"{len(書いた)} ファイルを {argv[1]} に書きました。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
