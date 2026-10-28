"""「○選」の縦長の1枚の画像を作り、上から下へゆっくり流すリールにする（費用なし。Claude Code だけで作る）。

2026-10-28 代表（統括経由）「こういう○選の画像を作ってリールとして投稿してみて」
見本は「保存版 福井で食べたいランチ10選」（黒地に金・朱の和風、1〜10の番号・店名・種類の帯、下に注意と出典）。

使い方:
  python scripts/まとめリール.py 台本.json 出力フォルダ [--bgm BGM.mp3] [--fonts fonts.css]

  出力フォルダに まとめ.png（縦長の画像）、threads.mp4・ig.mp4（おわりの案内がちがう）を作る。

台本.json（書くのは公式で確かめた事実だけ）:
  {
    "badge": "保存版",
    "title": "2026年オープン\\n福井の新しいカフェ7選",
    "subtitle": "パンとコーヒーから、野菜のパンケーキまで",
    "items": [
      {"name": "CAFE CON TE", "tag": "パンとコーヒー", "place": "福井市 MARUNOUCHI FUKURA",
       "text": "パン屋の2号店に併設", "open": "2026年5月オープン",
       "source": "https://..."},
      ...
    ],
    "note": "営業時間・定休日・メニューは変わることがあります。お出かけ前に公式の情報をご確認ください。"
  }

お店の写真は使わない（お店の許可が要る。代表 10/28）。料理の絵を入れるときは「写真はイメージです」を入れる。
BGM・フォントは公開リポジトリに入れない。--fonts には Google Fonts の CSS を落として url をローカルにしたものを渡す
（Shippori Mincho B1 と Zen Kaku Gothic New）。無ければ端末にある明朝・ゴシックで描く。
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE_W = 1080           # 画像を描く幅（動画は 720 に縮める）
HEAD_H = 760            # 見出しの高さ
ITEM_H = 330            # 1件の高さ
FOOT_BASE = 480         # 注意・出典の見出し・下の名前の高さ（出典の行は別に足す）
SOURCE_LINE = 44        # 出典1行の高さ
HOLD_TOP = 2.5          # はじめに止める秒
HOLD_END = 1.5          # 下まで来て止める秒
SPEED = 130             # 流れる速さ（動画の px／秒、720 幅で）
OUTRO_SEC = 2.5

_spec = importlib.util.spec_from_file_location("リール", Path(__file__).with_name("リール.py"))
リール = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(リール)
W, H, FPS = リール.W, リール.H, リール.FPS


def 高さ(台本: dict) -> int:
    return HEAD_H + ITEM_H * len(台本["items"]) + FOOT_BASE + SOURCE_LINE * len(台本["items"])


def ページ(台本: dict, fonts_css: str = "") -> str:
    e = html.escape
    items = "\n".join(f"""
      <section class="item">
        <div class="num">{i}</div>
        <div class="body">
          <div class="top"><span class="tag">{e(it["tag"])}</span><span class="open">{e(it.get("open", ""))}</span></div>
          <h2>{e(it["name"])}</h2>
          <p class="place">{e(it["place"])}</p>
          <p class="text">{e(it["text"])}</p>
        </div>
      </section>""" for i, it in enumerate(台本["items"], 1))
    sources = "\n".join(f'<li><b>{e(it["name"])}</b> {e(it["source"])}</li>' for it in 台本["items"])
    title = "<br>".join(e(x) for x in 台本["title"].split("\n"))
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<style>
{fonts_css}
:root {{ --bg:#140f0c; --ink:#f4ead8; --gold:#d6b46a; --gold2:#a8843f; --red:#c23a2b; --muted:#bfae93; }}
* {{ box-sizing:border-box; margin:0; }}
html,body {{ width:{PAGE_W}px; height:{高さ(台本)}px; background:var(--bg); color:var(--ink);
  font-family:"Zen Kaku Gothic New","IPAGothic",sans-serif; overflow:hidden; }}
body {{ background:
  radial-gradient(circle at 0 0, transparent 38px, rgba(214,180,106,.07) 39px, transparent 41px) 0 0/80px 40px,
  radial-gradient(circle at 40px 20px, transparent 38px, rgba(214,180,106,.07) 39px, transparent 41px) 0 0/80px 40px,
  var(--bg); }}
.mincho {{ font-family:"Shippori Mincho B1","IPAMincho",serif; }}
header {{ height:{HEAD_H}px; padding:150px 70px 0; text-align:center; border-bottom:3px double var(--gold2); }}
.badge {{ display:inline-block; background:var(--red); color:#fff; font-weight:700; font-size:40px;
  padding:10px 34px; letter-spacing:.2em; border:2px solid var(--gold); }}
h1 {{ font-family:"Shippori Mincho B1",serif; font-weight:800; font-size:84px; word-break:keep-all; line-height:1.3; color:var(--gold);
  margin-top:44px; text-shadow:0 3px 0 #000; }}
.sub {{ font-size:38px; color:var(--muted); margin-top:36px; }}
.rule {{ width:520px; height:6px; margin:44px auto 0; background:linear-gradient(90deg,transparent,var(--red),transparent); }}
.item {{ height:{ITEM_H}px; display:flex; gap:40px; align-items:center; padding:0 70px; border-bottom:1px solid rgba(214,180,106,.25); }}
.num {{ flex:0 0 130px; height:130px; border-radius:50%; border:4px solid var(--gold); color:var(--gold);
  font-family:"Shippori Mincho B1",serif; font-weight:800; font-size:76px; display:flex; align-items:center; justify-content:center;
  background:radial-gradient(circle,#2a1d14,#140f0c); }}
.body {{ flex:1; min-width:0; }}
.top {{ display:flex; gap:20px; align-items:center; }}
.tag {{ background:var(--gold); color:#1a120c; font-weight:700; font-size:30px; padding:6px 18px; }}
.open {{ color:var(--red); font-weight:700; font-size:30px; filter:brightness(1.35); }}
h2 {{ font-family:"Shippori Mincho B1",serif; font-weight:800; font-size:56px; margin-top:16px; line-height:1.2; }}
.place {{ font-size:32px; color:var(--muted); margin-top:10px; }}
.text {{ font-size:32px; margin-top:6px; }}
footer {{ padding:60px 70px 0; height:{FOOT_BASE + SOURCE_LINE * len(台本["items"])}px; position:relative; }}
.note {{ font-size:32px; line-height:1.6; border:2px solid var(--gold2); padding:24px 28px; color:var(--ink); }}
.src {{ margin-top:40px; color:var(--muted); font-size:26px; }}
.src li {{ list-style:none; height:{SOURCE_LINE}px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.src b {{ color:var(--ink); }}
.brand {{ position:absolute; left:0; right:0; bottom:50px; text-align:center; color:var(--gold); font-size:34px; letter-spacing:.15em; }}
</style></head><body>
<header>
  <div class="badge">{e(台本.get("badge", "保存版"))}</div>
  <h1>{title}</h1>
  <p class="sub">{e(台本.get("subtitle", ""))}</p>
  <div class="rule"></div>
</header>
{items}
<footer>
  <p class="note">{e(台本["note"])}</p>
  <ul class="src"><li>出典</li>{sources}</ul>
  <div class="brand">ふくいおでかけ</div>
</footer>
</body></html>"""


def 撮る(html_path: Path, png: Path, height: int) -> None:
    chrome = shutil.which("chromium") or shutil.which("google-chrome") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    subprocess.run([chrome, "--headless=new", "--no-sandbox", "--hide-scrollbars", "--disable-gpu",
                    f"--window-size={PAGE_W},{height + 300}", f"--screenshot={png}", "--virtual-time-budget=8000",
                    html_path.as_uri()], check=True, capture_output=True)
    # 窓の大きさどおりに撮れないことがあるので、少し大きく撮ってページの高さに切りそろえる
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(png), "-vf", f"crop={PAGE_W}:{height}:0:0",
                    str(png.with_suffix(".tmp.png"))], check=True)
    png.with_suffix(".tmp.png").replace(png)


def 動画(png: Path, out: Path, kind: str, bgm: Path | None, tmp: Path, height: int) -> float:
    img_h = round(height * W / PAGE_W)
    move = max(img_h - H, 0)
    scroll = move / SPEED
    body = HOLD_TOP + scroll + HOLD_END
    total = body + OUTRO_SEC
    t = リール.文字(tmp)
    handle = リール.HANDLES[kind]
    outro = [t("くわしくは", 52, "420", shadow=False), t("ふくいおでかけ で", 76, "500", shadow=False),
             t(handle[0], 48, "640", shadow=False)]
    if len(handle) > 1:
        outro.append(t(handle[1], 34, "705", shadow=False))
    chains = [
        f"[0:v]scale={W}:-2,crop={W}:{H}:0:'min(max(0,(t-{HOLD_TOP})*{SPEED}),{move})',"
        f"fps={FPS},format=yuv420p,setsar=1,trim=0:{body:.3f},setpts=PTS-STARTPTS[v0]",
        f"color=c={リール.ORANGE}:s={W}x{H}:r={FPS}:d={OUTRO_SEC},format=yuv420p,setsar=1," + ",".join(outro) + "[v1]",
        "[v0][v1]concat=n=2:v=1:a=0[v]",
    ]
    inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{body:.3f}", "-i", str(png)]
    if bgm:
        inputs += ["-i", str(bgm)]
        chains.append(f"[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume=0.8,"
                      f"afade=t=in:st=0:d=0.5,afade=t=out:st={total - 2.5:.3f}:d=2.5[a]")
    else:
        chains.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{total:.3f}[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";\n".join(chains),
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}",
                    "-movflags", "+faststart", str(out)], check=True)
    return total


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="○選の縦長画像を流すリールを作る")
    p.add_argument("script", type=Path)
    p.add_argument("out_dir", type=Path)
    p.add_argument("--bgm", type=Path)
    p.add_argument("--fonts", type=Path, help="ローカルの url にした Google Fonts の CSS")
    a = p.parse_args(argv)

    台本 = json.loads(a.script.read_text(encoding="utf-8"))
    for it in 台本["items"]:
        for k in ("name", "tag", "place", "text", "source"):
            if not it.get(k):
                print(f"台本の {k} が空です：{it}", file=sys.stderr)
                return 1
    a.out_dir.mkdir(parents=True, exist_ok=True)
    height = 高さ(台本)
    fonts_css = a.fonts.read_text(encoding="utf-8") if a.fonts else ""
    # フォントの CSS は相対の url なので、CSS と同じフォルダに HTML を置く
    html_dir = a.fonts.parent if a.fonts else a.out_dir
    html_path = html_dir / "まとめ.html"
    html_path.write_text(ページ(台本, fonts_css), encoding="utf-8")
    png = a.out_dir / "まとめ.png"
    撮る(html_path, png, height)
    with tempfile.TemporaryDirectory() as d:
        for kind in ("threads", "ig"):
            sec = 動画(png, a.out_dir / f"{kind}.mp4", kind, a.bgm, Path(d), height)
            print(f"できた：{a.out_dir / f'{kind}.mp4'}（{sec:.1f}秒）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
