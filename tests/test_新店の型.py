import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_shop_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class 新店の型のテスト(unittest.TestCase):
    """2026-10-24 代表「任せるからすぐに対処して」：新店の投稿の型と、検索語の分け方"""

    def test_検索語は催し_お店_施設の3つ(self):
        お店 = compose.検索語_お店
        self.assertTrue(compose.検索語あり(f"本文\n\n{お店}"))
        self.assertTrue(compose.検索語あり(f"本文\n\n{compose.検索語}"))
        self.assertEqual(compose.検索語を外す(f"本文\n\n{compose.検索語_おでかけ}"), "本文")

    def test_数字の書き出しの新店は気づく(self):
        t = f"鶏ガラ約10羽分の出汁。坂井市春江町に「越ノ龍」がオープンしました。\n\n{compose.検索語_お店}"
        if compose.検索語_お店 != compose.検索語:
            self.assertIn("店名", compose.新店の型の気づき(t))

    def test_型どおりの新店と催しは気づかない(self):
        t = f"坂井市春江町のラーメン店「越ノ龍」が10月1日にオープンしました。\n鶏ガラ約10羽分の出汁。\n\n{compose.検索語_お店}"
        self.assertIsNone(compose.新店の型の気づき(t))
        self.assertIsNone(compose.新店の型の気づき(f"10時から。オープンガーデンが開かれます。\n\n{compose.検索語}"))
    def test_型より前の新店の予備は使わない(self):
        古い = f"福井駅から徒歩7分。「御宿 野乃福井」がオープンしたそうです。\n\n{compose.検索語}"
        self.assertTrue(compose.型より前の新店(古い))
        新しい = f"福井市の宿「御宿 野乃福井」が10月1日にオープンしました。\n大浴場があります。\n\n{compose.検索語_おでかけ}"
        self.assertFalse(compose.型より前の新店(新しい))
        self.assertFalse(compose.型より前の新店(f"10時から。オープンガーデンが開かれます。\n\n{compose.検索語}"))
    def test_新店の直しを見つける(self):
        if compose.検索語_お店 == compose.検索語:
            return
        g = compose.検索語_お店
        # 10/26 ぶん：言い切っていない・数字の書き出し・催しの検索語のまま
        self.assertIn("そうです", compose.新店の直し(f"福井市の天ぷら店「たかさか」ができたそうです。\n\n{g}"))
        self.assertIn("名前", compose.新店の直し(f"高さ約6mの立体迷路。越前市に「らくまるパーク」がオープンしました。\n\n{compose.検索語_おでかけ}"))
        self.assertIn("検索語", compose.新店の直し(f"福井市に天ぷら店「たかさか」がオープンしました。\n\n{compose.検索語}"))
        self.assertIsNone(compose.新店の直し(f"福井市の天ぷら店「たかさか」が10月1日にオープンしました。\n\n{g}"))
        # 催しの投稿は見ない
        self.assertIsNone(compose.新店の直し(f"10月31日、勝山市で「ダイナソーフェス」が開かれるそうです。\n\n{compose.検索語}"))


if __name__ == "__main__":
    unittest.main()
