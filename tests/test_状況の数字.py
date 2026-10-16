import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location("状況", Path(__file__).resolve().parents[1] / "scripts" / "状況の数字.py")
状況 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(状況)


class 状況の数字のテスト(unittest.TestCase):
    def test_出した日ごとに足し_今日と31日前は入れない(self):
        今日 = date(2026, 10, 17)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "posted.json"
            p.write_text(json.dumps({"posted": {
                "a": {"post_id": "1", "posted_at": "2026-10-15T23:00:00+00:00"},  # JST 10/16
                "b": {"post_id": "2", "posted_at": "2026-10-16T01:00:00+00:00"},  # JST 10/16
                "c": {"post_id": "3", "posted_at": "2026-10-17T00:00:00+00:00"},  # JST 10/17（今日）
                "d": {"post_id": "4", "posted_at": "2026-09-16T00:00:00+00:00"},  # 31日前
                "e": {"post_id": "5", "posted_at": "2026-10-05T00:00:00+00:00"},
            }}))
            投稿 = 状況.出した投稿(今日, p)
        self.assertEqual(sorted(x[1] for x in 投稿), ["1", "2", "5"])
        数 = {"1": {"views": 10, "likes": 1}, "2": {"views": 5}, "5": {"views": 100}}
        日ごと = 状況.日ごとに足す(投稿, 数, 今日)
        self.assertEqual(len(日ごと), 30)
        self.assertEqual(日ごと[-1]["日"], "2026-10-16")
        self.assertEqual((日ごと[-1]["投稿"], 日ごと[-1]["views"], 日ごと[-1]["likes"]), (2, 15, 1))
        self.assertEqual(状況.合計(日ごと, 7)["views"], 15)
        self.assertEqual(状況.合計(日ごと, 30)["views"], 115)

    def test_フォロワーは同じ日を上書き(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.jsonl"
            p.write_text('{"日": "2026-10-16", "フォロワー": 10}\n{"日": "2026-10-17", "フォロワー": 11}\n')
            r = 状況.フォロワーを足す(p, "2026-10-17", 12)
        self.assertEqual([x["フォロワー"] for x in r], [10, 12])


if __name__ == "__main__":
    unittest.main()
