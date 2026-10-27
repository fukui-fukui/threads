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


if __name__ == "__main__":
    unittest.main()
