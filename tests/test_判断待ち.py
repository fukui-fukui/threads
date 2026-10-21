import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("judge_for_test", ROOT / "scripts" / "判断待ち.py")
判断 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(判断)


def 地域を作る(d: Path, 投稿: list[dict]) -> None:
    (d / "neta").mkdir()
    (d / "posts").mkdir()
    (d / "state").mkdir()
    (d / "neta" / "ネタ帳.md").write_text("### 2026-10-19\n- なにか\n", encoding="utf-8")
    (d / "state" / "インスタ新着.json").write_text(
        json.dumps({"集めた日": "2026-10-19", "投稿": 投稿}, ensure_ascii=False), encoding="utf-8")


class インスタの引用(unittest.TestCase):
    def test_PRの投稿は引用できない(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            地域を作る(d, [
                {"アカウント": "Instagram @a_fukui", "日付": "2026-10-18", "本文": "a_fukui 新しいカフェ", "url": "https://www.instagram.com/p/1/"},
                {"アカウント": "Instagram @b_fukui", "日付": "2026-10-18", "本文": "b_fukui #PR 新商品", "url": "https://www.instagram.com/p/2/"},
            ])
            出 = 判断.インスタを読む(d, "ふくいおでかけ", date(2026, 10, 10))
            self.assertEqual([x["引用できる"] for x in 出], [True, False])
            self.assertEqual(出[0]["アカウント"], "a_fukui")

    def test_コメントがあるものだけ入れる(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            地域を作る(d, [])
            共通 = {"出どころ": "ふくいおでかけ", "種類": "インスタ（Meta）で読んだ新しい投稿", "答え": "引用",
                    "アカウント": "a_fukui", "url": "https://www.instagram.com/p/1/", "引用できる": True}
            済み = 判断.反映([
                {**共通, "id": "aaaaaaaa1", "一言": "秋の新作、気になります"},
                {**共通, "id": "bbbbbbbb2", "一言": ""},
                {**共通, "id": "cccccccc3", "一言": "これも", "引用できる": False},
            ], {"fukui": d})
            self.assertEqual(済み, ["aaaaaaaa1"])
            行 = [json.loads(l) for l in (d / "posts" / "queue.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(行), 1)
            self.assertIn("@a_fukui さんの投稿で紹介されていました", 行[0]["text"])
            self.assertTrue(行[0]["text"].startswith("秋の新作、気になります"))
            self.assertIn("https://www.instagram.com/p/1/", 行[0]["thread"][0])
            self.assertTrue(行[0]["approved_at"])


if __name__ == "__main__":
    unittest.main()
