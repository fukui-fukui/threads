import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_season_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


def 投稿(d, text, 時=19):
    return {"id": d, "scheduled_at": f"{d}T{時}:00:00+09:00", "text": text + f"\n\n{compose.検索語_おでかけ}",
            "thread": ["出典元：https://example.com/illumi"]}


一回目 = "鯖江市の西山公園で「西山公園ライトアップ」が11月1日から11月30日まで開かれています。\nもみじが池に映り、17時から21時まで点灯します。"
二回目 = "鯖江市「西山公園ライトアップ」は、駐車場が公園の北と南にあり、どちらも無料です。\n見ごろは11月中旬から下旬と案内されています。"


@unittest.skipUnless(compose.同じ名を見る, "同じ名を見ない地域")
class SeasonalWeeklyTest(unittest.TestCase):
    # 2026-11-07 代表「紅葉、イルミネーションなどの期間限定・季節限定イベントは週1ペースで複数回投稿して」

    def test_detect(self):
        self.assertTrue(compose.季節ものの投稿({"text": 一回目}, date(2026, 11, 8)))
        # 期間が2週間より短い催しは季節ものとみない
        self.assertFalse(compose.季節ものの投稿({"text": "「秋の紅葉まつり」は11月8日から11月9日まで。"}, date(2026, 11, 8)))
        self.assertFalse(compose.季節ものの投稿({"text": "福井市のカフェ「テスト珈琲」。"}, date(2026, 11, 8)))
        # 年をまたぐ期間
        self.assertTrue(compose.季節ものの投稿({"text": "「テストイルミネーション」は12月1日から1月12日まで。"}, date(2026, 12, 5)))

    def test_twice_a_week(self):
        # 同日の変更「週に2回くらい」：3日あければ出してよい
        記 = compose.名の記録([投稿("2026-11-05", 一回目)], date(2026, 11, 8))
        self.assertIsNone(compose.名で止める理由(投稿("2026-11-08", 二回目), 記))

    def test_not_seasonal(self):
        # 2026-11-07 開発・ぎふあいち
        日 = date(2026, 11, 9)
        self.assertFalse(compose.季節ものの投稿({"text": "多治見市の「多治見市モザイクタイルミュージアム」で企画展が12月27日まで。"}, 日))
        self.assertFalse(compose.季節ものの投稿({"text": "10月31日（土）と11月1日（日）、「2026いぶきやま紅葉祭」が開かれます。"}, 日))
        self.assertFalse(compose.季節ものの投稿({"text": "名古屋の「オアシス21 水の宇宙船」は、毎晩ライトアップされます。"}, 日))
        self.assertFalse(compose.季節ものの投稿({"text": "11月14日（土）、「テスト紅葉ウォーク」が開かれます。"}, 日))
        self.assertTrue(compose.季節ものの投稿({"text": "「香嵐渓もみじまつり」は11月30日まで。"}, 日))

    def test_names(self):
        e = {"text": "「Aichi Now」によると、豊田市の「香嵐渓もみじまつり」は11月30日まで。", "note": "「同じ問いかけは14日くり返さない」"}
        self.assertEqual(compose.季節の名(e), {"香嵐渓もみじまつり"})
        e = {"text": "蒲郡市の「ラグーナテンボス」で「神秘のシャイニングアーチ」が2月まで点灯しています。\n12月1日から。"}
        self.assertEqual(compose.季節の名(e), {"ラグーナテンボス", "神秘のシャイニングアーチ"})
        記 = compose.名の記録([投稿("2026-11-01", e["text"])], date(2026, 11, 8))
        self.assertEqual(compose.季節の週1の一覧(記).count("\n- "), 0)   # 同じ投稿の名前は1行

    def test_same_event_other_name_is_one_line(self):
        a = 投稿("2026-10-18", "12月15日まで、中能登町の「mii cafe」で「mii cafe 紅葉アフタヌーンティー」が出ています。")
        b = 投稿("2026-10-26", "12月15日まで、中能登町のカフェで「紅葉アフタヌーンティー」が出ています。9月15日から。")
        一覧 = compose.季節の週1の一覧(compose.名の記録([a, b], date(2026, 11, 8)))
        self.assertEqual(一覧.count("（前回"), 1)
        self.assertIn("2026-10-26", 一覧)

    def test_weekly_allowed_after_7_days(self):
        記 = compose.名の記録([投稿("2026-11-01", 一回目)], date(2026, 11, 8))
        self.assertIsNone(compose.名で止める理由(投稿("2026-11-08", 二回目), 記))
        self.assertIn("西山公園ライトアップ", compose.季節の週1の一覧(記))
        self.assertIn("前回書いたこと", compose.季節の週1の一覧(記))
        self.assertNotIn("西山公園ライトアップ", compose.使えない名の一覧(記).split("###")[0])

    def test_ended_is_not_listed(self):
        終わった = "「テスト紅葉ライトアップ」は10月20日から11月3日まで、18時から点灯します。"
        記 = compose.名の記録([投稿("2026-10-25", 終わった)], date(2026, 11, 8))
        self.assertEqual(compose.季節の週1の一覧(記), "")

    def test_within_7_days_is_stopped(self):
        記 = compose.名の記録([投稿("2026-11-06", 一回目)], date(2026, 11, 8))
        self.assertIn("週2回", compose.名で止める理由(投稿("2026-11-08", 二回目), 記))
        self.assertEqual(compose.季節の週1の一覧(記), "")

    def test_same_words_are_stopped(self):
        記 = compose.名の記録([投稿("2026-11-01", 一回目)], date(2026, 11, 8))
        self.assertIn("切り口", compose.名で止める理由(投稿("2026-11-08", 一回目), 記))

    def test_third_week(self):
        記 = compose.名の記録([投稿("2026-11-01", 一回目), 投稿("2026-11-08", 二回目)], date(2026, 11, 15))
        三回目 = "鯖江市「西山公園ライトアップ」は11月30日まで。\nJR鯖江駅から歩いて約15分です。"
        self.assertIsNone(compose.名で止める理由(投稿("2026-11-15", 三回目), 記))

    def test_source_limit_not_applied(self):
        記 = {"https://example.com/illumi": [("2026-11-01", 19), ("2026-11-08", 19)]}
        self.assertIsNotNone(compose.出典で止める理由({"https://example.com/illumi"}, 記, date(2026, 11, 15)))
        self.assertIsNone(compose.出典で止める理由({"https://example.com/illumi"}, 記, date(2026, 11, 15), 季節=True))
        # 3日あけるのはそのまま
        self.assertIsNotNone(compose.出典で止める理由({"https://example.com/illumi"}, 記, date(2026, 11, 9), 季節=True))

    def test_old_start_exception(self):
        文 = "「テストツリーファンタジー」は9月20日から12月25日まで、毎日17時に点灯します。"
        self.assertIsNotNone(compose.古い催し(文, date(2026, 11, 8)))
        self.assertTrue(compose.季節の期間中(文, date(2026, 11, 8)))
        # 終わった季節もの・ふつうの催しは例外にしない
        self.assertFalse(compose.季節の期間中("「テスト紅葉ライトアップ」は9月1日から10月31日まで。", date(2026, 11, 8)))
        self.assertFalse(compose.季節の期間中("「テスト展」は7月3日から上映。", date(2026, 11, 8)))


if __name__ == "__main__":
    unittest.main()
