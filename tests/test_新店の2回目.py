import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_second_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


def 投稿(d, text):
    return {"id": d, "scheduled_at": f"{d}T17:00:00+09:00", "text": text + f"\n\n{compose.検索語_お店}"}


@unittest.skipUnless(compose.同じ名を見る, "同じ名を見ない地域")
class SecondTimeTest(unittest.TestCase):
    # 2026-11-03 代表「（新店の）2回目は10日以内に実施に変更」
    一回目 = "10月28日（水）にオープンした、福井市のカフェ「テスト珈琲」。\n\nオープンおめでとうございます。"
    二回目 = 投稿("2026-11-03", "10月28日（水）にオープンした、福井市のカフェ「テスト珈琲」。\n看板はプリンです。\n\nオープンおめでとうございます。")

    def test_second_within_10_days(self):
        記 = compose.名の記録([投稿("2026-10-28", self.一回目)], date(2026, 11, 3))
        self.assertIsNone(compose.名で止める理由(self.二回目, 記))
        self.assertIn("テスト珈琲", compose.新店の2回目の一覧(記))
        self.assertIn("1回目に書いた売り", compose.新店の2回目の一覧(記))
        self.assertNotIn("テスト珈琲", compose.使えない名の一覧(記).split("###")[0])

    def test_after_10_days_or_third(self):
        記 = compose.名の記録([投稿("2026-10-22", self.一回目)], date(2026, 11, 3))
        self.assertIsNotNone(compose.名で止める理由(self.二回目, 記))
        記 = compose.名の記録([投稿("2026-10-25", self.一回目), 投稿("2026-10-30", self.一回目)], date(2026, 11, 3))
        self.assertIsNotNone(compose.名で止める理由(self.二回目, 記))
        記 = compose.名の記録([投稿("2026-11-02", self.一回目)], date(2026, 11, 3))   # 3日あける
        self.assertIsNotNone(compose.名で止める理由(self.二回目, 記))

    def test_ordinary_shop_keeps_14_days(self):
        記 = compose.名の記録([投稿("2026-10-28", "福井市のカフェ「テスト珈琲」は2019年に開いた店です。")], date(2026, 11, 3))
        self.assertIsNotNone(compose.名で止める理由(self.二回目, 記))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(compose.同じ名を見る, "同じ名を見ない地域")
class ThirdTimeTest(unittest.TestCase):
    def test_first_time_older_than_14_days_counts(self):
        # 1回目が15日より前でも数える（橋架：10/20 と 10/28 に出ていて、11/5 は3回目）
        一 = SecondTimeTest.一回目
        記 = compose.名の記録([投稿("2026-10-20", 一), 投稿("2026-10-28", 一)], date(2026, 11, 5))
        self.assertIsNotNone(compose.名で止める理由(SecondTimeTest.二回目, 記))
        self.assertEqual(compose.新店の2回目の一覧(記), "")
