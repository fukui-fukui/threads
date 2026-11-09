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
    一回目 = "10月28日（水）にオープンした、福井市のカフェ「テスト珈琲」。\n看板は「季節のタルト」です。\n\nオープンおめでとうございます。"
    二回目 = 投稿("2026-11-03", "10月28日（水）にオープンした、福井市のカフェ「テスト珈琲」。\n看板はプリンです。\n\nオープンおめでとうございます。")

    def test_second_within_10_days(self):
        記 = compose.名の記録([投稿("2026-10-28", self.一回目)], date(2026, 11, 3))
        self.assertIsNone(compose.名で止める理由(self.二回目, 記))
        self.assertIn("テスト珈琲", compose.新店の2回目の一覧(記))
        self.assertIn("1回目に書いたこと（本文と返信。くり返さない）：", compose.新店の2回目の一覧(記))
        self.assertIn("看板は「季節のタルト」です。", compose.新店の2回目の一覧(記))
        self.assertNotIn("季節のタルト」（", compose.新店の2回目の一覧(記))   # メニュー名は店として並べない
        # 2回目の文に「オープン」が無くても通す（11/4 石川）
        self.assertIsNone(compose.名で止める理由(投稿("2026-11-03", "福井市のカフェ「テスト珈琲」は、プリンが看板です。"), 記))
        self.assertNotIn("テスト珈琲", compose.使えない名の一覧(記).split("###")[0])

    def test_second_that_repeats_first_is_stopped(self):
        # 2026-11-05 ぎふあいち：ヒロキチ商店の2回目が1回目と同じ（築100年の古民家）だった。言葉が大きく重なれば予備に替える
        一回目 = {"id": "a", "scheduled_at": "2026-10-28T21:00:00+09:00",
                "text": "西尾市肴町の築100年以上の古民家に、シェアキッチン兼お土産屋「ヒロキチ商店」が、11月7日（土）にオープン予定です。\n\nキッチンとお土産の店が、同じ古民家の中にできます。\n\n" + compose.検索語_お店,
                "thread": ["西尾｜ヒロキチ商店\n築100年以上の古民家を使ったシェアキッチン兼お土産屋です。営業時間は記事に書かれていません。\n出典元：https://example.com/a"]}
        記 = compose.名の記録([一回目], date(2026, 11, 6))
        同じ = 投稿("2026-11-06", "11月7日（土）オープン、西尾市肴町のシェアキッチン兼お土産屋「ヒロキチ商店」。\n\n築100年以上の古民家を使った店です。\n\nオープンおめでとうございます。")
        同じ["thread"] = ["西尾｜ヒロキチ商店\n築100年以上の古民家が舞台です。営業時間は出典に載っていません。\n出典元：https://example.com/a"]
        self.assertIn("同じ言葉ばかり", compose.名で止める理由(同じ, 記) or "")
        別 = 投稿("2026-11-06", "11月7日（土）オープン、西尾市肴町のシェアキッチン兼お土産屋「ヒロキチ商店」。\n\n西尾の抹茶を使った焼き菓子や、地元の作家の器を並べるそうです。週末はキッチンで日替わりの店主が料理を出します。")
        self.assertIsNone(compose.名で止める理由(別, 記))

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
