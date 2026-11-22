import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compose  # noqa: E402


class ノートのテスト(unittest.TestCase):
    def test_外した理由の文を落とす(self):
        n = compose.ノートを短く("先の予定／A展（10日後）→不可。代わりにB展は11/20使用済み。C は日付不明。D展を使用。")
        self.assertEqual(n, "先の予定／D展を使用。")

    def test_短いものはそのまま(self):
        self.assertEqual(compose.ノートを短く("土地の言葉／問いかけ型"), "土地の言葉／問いかけ型")

    def test_改行をつなぎ上限で切る(self):
        n = compose.ノートを短く("一行目\n" + "、".join(["ながいネタ"] * 40))
        self.assertNotIn("\n", n)
        self.assertLessEqual(len(n), 120)
        self.assertTrue(n.endswith("…"))


if __name__ == "__main__":
    unittest.main()
