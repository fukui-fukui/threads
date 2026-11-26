"""14:00 の土地の言葉の問いで、材料に無い言葉の例を外す（2026-11-21 統括：「ほかす」「けったいな」が出典なしで入った）"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compose  # noqa: E402

問い = "県外の人と話していて、通じなかった言葉。\n\n・ほかす　・つる　・けったいな\n\n1つだけ挙げるなら、何でしょう？\n\n福井の人の「通じなかった言葉」を教えてください。"


class 言葉の例(unittest.TestCase):
    def test_材料に無い例の行を外す(self):
        文, 外した = compose.材料に無い言葉の例を外す(問い, "- 福井では机を運ぶことを「つる」と言う")
        self.assertNotIn("ほかす", 文)
        self.assertEqual(外した, ["ほかす", "けったいな"])
        self.assertIn("1つだけ挙げるなら、何でしょう？", 文)
        self.assertIn("教えてください", 文)

    def test_全部材料にあれば残す(self):
        文, 外した = compose.材料に無い言葉の例を外す(問い, "ほかす つる けったいな")
        self.assertEqual(文, 問い)
        self.assertEqual(外した, [])

    def test_言葉の問いでなければ見ない(self):
        t = "寒くなったら家でまず作るものは？\n・おでん　・鍋　・豚汁\nうちはこれ、を教えてください。"
        self.assertEqual(compose.材料に無い言葉の例を外す(t, ""), (t, []))


if __name__ == "__main__":
    unittest.main()


class 問いの本体を残す(unittest.TestCase):
    """2026-11-26 運用部・福井：「おや？」を含む1行目（問いの本体）が外れ、問いの無い投稿になった。"""

    def test_最初の行は残す(self):
        import compose
        t = "県外の人と話していて、「おや？」という顔をされた福井の話し方。\n言葉そのものでも構いません。\n\n福井の人の「県外で面白がられた話し方」を教えてください。"
        出, _ = compose.材料に無い言葉の例を外す(t, "")
        self.assertTrue(出.startswith("県外の人と話していて"))

    def test_声は言葉の例に数えない(self):
        import compose
        t = "県外で通じなかった福井の言葉は？\n\n「えっ！」と言われたものを。\n\n教えてください。"
        出, 外した = compose.材料に無い言葉の例を外す(t, "")
        self.assertEqual(外した, [])
