import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("リール", Path(__file__).resolve().parents[1] / "scripts" / "リール.py")
リール = importlib.util.module_from_spec(spec)
spec.loader.exec_module(リール)

台本 = {"date": "10/24(土)・25(日)", "scenes": [
    {"clip": f"{i}.mp4", "name": f"イベント{i}", "date": "10/24(土)", "place": "福井市", "point": "見どころ"}
    for i in (1, 2, 3)
]}


class リールのテスト(unittest.TestCase):
    def 作る(self, kind, bgm=None):
        with tempfile.TemporaryDirectory() as d:
            cmd = リール.組み立て(台本, Path("/x"), Path(d) / "o.mp4", kind, bgm, Path(d), dry_run=True)
            texts = [p.read_text(encoding="utf-8") for p in Path(d).glob("t*.txt")]
        return cmd, texts

    def test_長い名前は小さくする(self):
        self.assertEqual(リール.大きさ("福井そば博", 56), 56)
        self.assertLess(リール.大きさ("とても長いイベントの名前がここに入ります", 56), 56)

    def test_Threads用とInstagram用でおわりの案内が変わる(self):
        _, t = self.作る("threads")
        self.assertIn("@fukui._.fukui", t)
        self.assertNotIn("@fukui._fukui", t)
        _, i = self.作る("ig")
        self.assertIn("@fukui._fukui", i)
        self.assertIn("（プロフィールのリンクから）", i)

    def test_どの場面にもイメージの注記と_おわりに公式の確認(self):
        _, t = self.作る("threads")
        self.assertEqual(t.count("※画像はイメージです"), 4)  # はじめ＋3場面
        self.assertIn("日時・内容は公式の情報をご確認ください", t)
        self.assertIn("来週末の福井 おでかけ3選 2/3", t)

    def test_BGMはフェードして20秒(self):
        cmd, _ = self.作る("ig", Path("/x/bgm.mp3"))
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("volume=0.8", fc)
        self.assertIn("afade=t=out:st=17.5:d=2.5", fc)
        self.assertEqual(cmd[cmd.index("-t") + 1], "20.0")

    def test_使い始めの秒を指定できる(self):
        台本2 = {**台本, "scenes": [{**台本["scenes"][0], "start": 1.5}, *台本["scenes"][1:]]}
        with tempfile.TemporaryDirectory() as d:
            cmd = リール.組み立て(台本2, Path("/x"), Path(d) / "o.mp4", "ig", None, Path(d), dry_run=True)
        i = cmd.index("/x/1.mp4")
        self.assertEqual(cmd[i - 3:i - 1], ["-ss", "1.5"])
        self.assertEqual(cmd[cmd.index("/x/2.mp4") - 2], "0")

    def test_静止画はゆっくり寄る動画にする(self):
        台本3 = {**台本, "scenes": [{**台本["scenes"][0], "clip": "1.png"}, *台本["scenes"][1:]]}
        with tempfile.TemporaryDirectory() as d:
            cmd = リール.組み立て(台本3, Path("/x"), Path(d) / "o.mp4", "ig", None, Path(d), dry_run=True)
        fc = cmd[cmd.index("-filter_complex") + 1]
        self.assertEqual(fc.count("zoompan"), 2)  # はじめと1場面目
        self.assertNotIn("[1:v]scale=1440", fc)


if __name__ == "__main__":
    unittest.main()
