"""「来週末の福井おでかけ3選」リールを、5秒の動画3本から ffmpeg で組み立てる。

2026-10-17 代表「イベント3選のリール作成投稿のチームを作って、必要ならスキルで登録しておいて。」
手順の全体は .claude/skills/event-reel/SKILL.md。ここはテロップ・はじめ・おわり・つなぎ・BGM だけ。

使い方:
  python scripts/リール.py 台本.json 出力フォルダ [--bgm BGM.mp3] [--dry-run]

  出力フォルダに threads.mp4（おわりが @fukui._.fukui）と ig.mp4（@fukui._fukui）を作る。
  --dry-run なら ffmpeg のコマンドを表示するだけ。

台本.json（文字は出典で確かめた事実だけ）:
  {
    "date": "10/24(土)・25(日)",
    "scenes": [
      {"clip": "1.mp4", "name": "福井そば博2026", "date": "10/24(土)・25(日)",
       "place": "福井駅前 ハピリン", "point": "そばの食べ比べ9ブース", "start": 1.5},
      ... 3つ（start は使い始めの秒。省略すると頭から）
    ]
  }
  clip は台本.json からの相対パスでもよい。静止画（.png・.jpg）なら、ゆっくり寄る5秒の動画にする。

BGM は公開リポジトリに入れない（代表の手元・Google ドライブ AI会社/BGM から持ってくる）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FONT = "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf"  # IPAPゴシック
W, H, FPS = 720, 1280, 24
SCENE_SEC = 5.0
INTRO_SEC = 2.5
OUTRO_SEC = 2.5
ORANGE = "0xE8873A"
YELLOW = "0xFFD54F"
NOTE_IMAGE = "※画像はイメージです"
NOTE_OFFICIAL = "日時・内容は公式の情報をご確認ください"
HANDLES = {
    "threads": ["@fukui._.fukui"],
    "ig": ["@fukui._fukui", "（プロフィールのリンクから）"],
}


class 文字:
    """drawtext の文字は textfile で渡す（: や ' のエスケープを避ける）。"""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.n = 0

    def __call__(self, text: str, size: int, y: str, color: str = "white", x: str = "(w-tw)/2",
                 box: str | None = None, shadow: bool = True) -> str:
        self.n += 1
        f = self.tmp / f"t{self.n}.txt"
        f.write_text(text, encoding="utf-8")
        opts = [f"fontfile={FONT}", f"textfile={f}", f"fontsize={size}", f"fontcolor={color}",
                f"x={x}", f"y={y}"]
        if box:
            opts += ["box=1", f"boxcolor={box}", "boxborderw=12"]
        if shadow:
            opts += ["shadowcolor=black@0.6", "shadowx=2", "shadowy=2"]
        return "drawtext=" + ":".join(opts)


def 大きさ(text: str, base: int, width: int = W - 60) -> int:
    """長い名前は横幅に収まるまで小さくする（全角1文字≒fontsize とみる）。"""
    return min(base, int(width / max(len(text), 1)))


def 正規化() -> str:
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},format=yuv420p"


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def 寄る() -> str:
    """静止画をゆっくり寄る5秒の動画にする（Vids の上限が少ないとき用。代表 10/22）。"""
    frames = int(SCENE_SEC * FPS)
    return (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
            f"zoompan=z='1+0.08*on/{frames}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={W}x{H}:fps={FPS},")


def 元(scenes: list[dict], i: int) -> str:
    """場面 i の映像の入り口。静止画なら先にゆっくり寄る動画にする。"""
    return f"[{i}:v]" + (寄る() if Path(scenes[i]["clip"]).suffix.lower() in IMAGE_EXT else "")


def 組み立て(台本: dict, base: Path, out: Path, kind: str, bgm: Path | None, tmp: Path,
           dry_run: bool) -> list[str]:
    t = 文字(tmp)
    scenes = 台本["scenes"]
    n = len(scenes)
    inputs: list[str] = []
    chains: list[str] = []

    for s in scenes:
        clip = Path(s["clip"])
        # 代表が Google Vids で作った動画は長いので、使い始めの秒（start）から5秒を使う
        if clip.suffix.lower() in IMAGE_EXT:
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(SCENE_SEC)]
        else:
            inputs += ["-ss", str(s.get("start", 0))]
        inputs += ["-i", str(clip if clip.is_absolute() else base / clip)]

    # はじめ：1本目の絵をぼかして題名
    chains.append(
        f"{元(scenes, 0)}{正規化()},trim=0:{INTRO_SEC},setpts=PTS-STARTPTS,gblur=sigma=18,"
        "drawbox=x=0:y=0:w=iw:h=ih:color=black@0.35:t=fill,"
        + ",".join([
            t("来週末の福井", 64, "430"),
            t(f"おでかけ{n}選", 104, "520", box=f"{ORANGE}@0.95"),
            t(台本["date"], 52, "690", color=YELLOW),
            t(NOTE_IMAGE, 24, "h-th-30", x="w-tw-24"),
        ])
        + "[intro]"
    )

    # 各場面：上に帯、帯の中に見出し・名前・日にち・場所・見どころ、右下に注記
    for i, s in enumerate(scenes):
        chains.append(
            f"{元(scenes, i)}{正規化()},trim=0:{SCENE_SEC},setpts=PTS-STARTPTS,"
            "drawbox=x=0:y=40:w=iw:h=360:color=black@0.45:t=fill,"
            + ",".join([
                t(f"来週末の福井 おでかけ{n}選 {i + 1}/{n}", 28, "62", box=f"{ORANGE}@1", shadow=False),
                t(s["name"], 大きさ(s["name"], 56), "130"),
                t(s["date"], 大きさ(s["date"], 40), "212", color=YELLOW),
                t(s["place"], 大きさ(s["place"], 34), "275"),
                t(s["point"], 大きさ(s["point"], 34), "330"),
                t(NOTE_IMAGE, 24, "h-th-30", x="w-tw-24"),
            ])
            + f"[s{i}]"
        )

    # おわり：オレンジの地に案内
    handle = HANDLES[kind]
    outro = [t("くわしくは", 52, "420", shadow=False),
             t("ふくいおでかけ で", 76, "500", shadow=False),
             t(handle[0], 48, "640", shadow=False)]
    if len(handle) > 1:
        outro.append(t(handle[1], 34, "705", shadow=False))
    outro.append(t(NOTE_OFFICIAL, 28, "h-th-120", shadow=False))
    chains.append(
        f"color=c={ORANGE}:s={W}x{H}:r={FPS}:d={OUTRO_SEC},format=yuv420p,setsar=1,"
        + ",".join(outro) + "[outro]"
    )

    order = "[intro]" + "".join(f"[s{i}]" for i in range(n)) + "[outro]"
    chains.append(f"{order}concat=n={n + 2}:v=1:a=0[v]")

    total = INTRO_SEC + SCENE_SEC * n + OUTRO_SEC
    if bgm:
        inputs += ["-i", str(bgm)]
        chains.append(
            f"[{n}:a]atrim=0:{total},asetpts=PTS-STARTPTS,volume=0.8,"
            f"afade=t=in:st=0:d=0.5,afade=t=out:st={total - 2.5}:d=2.5[a]"
        )
    else:
        chains.append(f"anullsrc=r=44100:cl=stereo,atrim=0:{total}[a]")

    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex", ";\n".join(chains),
           "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "160k", "-t", str(total), "-movflags", "+faststart", str(out)]
    if dry_run:
        print(" ".join(cmd))
    else:
        subprocess.run(cmd, check=True)
    return cmd


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="来週末の福井おでかけ3選リールを組み立てる")
    p.add_argument("script", type=Path, help="台本.json")
    p.add_argument("out_dir", type=Path, help="出力フォルダ")
    p.add_argument("--bgm", type=Path, help="BGM（公開リポジトリには入れない）")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)

    if not shutil.which("ffmpeg"):
        print("ffmpeg がありません", file=sys.stderr)
        return 1
    if not Path(FONT).exists():
        print(f"フォントがありません：{FONT}", file=sys.stderr)
        return 1
    台本 = json.loads(a.script.read_text(encoding="utf-8"))
    for k in ("name", "date", "place", "point", "clip"):
        for s in 台本["scenes"]:
            if not s.get(k):
                print(f"台本の {k} が空です：{s}", file=sys.stderr)
                return 1
    if a.bgm is None:
        print("BGM なしで作ります（無音）", file=sys.stderr)

    a.out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        for kind in ("threads", "ig"):
            out = a.out_dir / f"{kind}.mp4"
            組み立て(台本, a.script.parent, out, kind, a.bgm, Path(d), a.dry_run)
            if not a.dry_run:
                print(f"できた：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
