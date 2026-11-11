import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compose  # noqa: E402

水 = date(2026, 10, 28)
居酒屋 = "福井市の居酒屋「てんやわんや」。\n\n営業時間は15:00〜23:00、定休日は水曜日です。"
昼の店 = "金沢のカフェ「オギカフリーダ」。\n\n営業時間は11:00〜16:00、定休日は木曜です。"
催し = "10月31日、勝山市で「ダイナソーフェス」が開かれます。"


class 定休日のテスト(unittest.TestCase):
    """定休日・営業時間に合わない枠にお店を入れない（2026-10-27 統括・運用部 福井／石川）。"""

    def test_合わない理由(self):
        self.assertEqual(compose.合わない理由(居酒屋, 水, 17), "定休日の曜日")
        self.assertIn("16時に閉まる", compose.合わない理由(昼の店, 水, 17))
        self.assertIsNone(compose.合わない理由(昼の店, 水, 10))
        # 夜の枠は翌日に行く人向け。翌日（木）が定休日なら合わない
        self.assertIsNone(compose.合わない理由(昼の店, date(2026, 10, 27), 23))
        self.assertIsNotNone(compose.合わない理由(昼の店, 水, 23))
        self.assertIsNone(compose.合わない理由(催し, 水, 17))

    def test_並べ直す(self):
        ps = [{"hour": 6, "text": 催し}, {"hour": 10, "text": 催し}, {"hour": 17, "text": 昼の店}, {"hour": 19, "text": 居酒屋}]
        r = {p["hour"]: p["text"] for p in compose.定休日と時刻で並べ直す(ps, 水, {6})}
        self.assertEqual(r[10], 昼の店)   # 閉まったあとの枠から、開いている枠へ入れ替え
        self.assertEqual(r[17], 催し)
        self.assertNotIn(19, r)           # 定休日は外す（予備で埋める）

    def test_開館と夜の曜日(self):
        """「開館は」「昼は」の時刻、「夜の営業は金・土・日曜だけ」も見る（2026-11-11 運用部・石川：ATAKA TERRACE・やまねこ亭）。"""
        館 = "小松市の「ATAKA TERRACE」。\n開館は9:00〜17:00、水曜休みです。"
        self.assertEqual(compose.閉まる時(館), 17)
        self.assertIn("17時に閉まる", compose.合わない理由(館, date(2026, 11, 12), 18))
        カレー = "金沢の「やまねこ亭」。\n昼は11:30〜14:00（ラストオーダー）。夜の営業は金・土・日曜だけで、月・火曜が定休です。"
        self.assertEqual(compose.合わない理由(カレー, date(2026, 11, 12), 18), "夜の営業が無い曜日")
        self.assertIsNone(compose.合わない理由(カレー, date(2026, 11, 12), 10))
        # 時刻の無い「開店」の文が先にあっても、あとの営業時間を見る
        店 = "9月14日に開店。営業は11:00〜15:00と16:00〜20:00です。"
        self.assertEqual((compose.開く時(店), compose.閉まる時(店)), (11, 20))

    def test_定休日の文が二つ(self):
        """「定休日は出典でご確認ください」のあとに「定休日: 月曜」があるときも見る（2026-11-11 運用部・石川：鶏笑）。"""
        t = "営業時間・定休日は出典でご確認ください。\n営業時間: 11:00-15:00／定休日: 月曜（https://example.com/）"
        self.assertTrue(compose.定休日に当たる(t, date(2026, 11, 16)))


if __name__ == "__main__":
    unittest.main()
