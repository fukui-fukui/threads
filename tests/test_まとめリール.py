import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("まとめ", Path(__file__).resolve().parents[1] / "scripts" / "まとめリール.py")
まとめ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(まとめ)

台本 = {"title": "福井の\nカフェ<3>選", "subtitle": "s", "note": "営業時間は変わることがあります。",
        "items": [{"name": f"店{i}", "tag": "t", "place": "p", "text": "x", "source": f"https://e/{i}"} for i in range(3)]}


class まとめリールのテスト(unittest.TestCase):
    def test_高さは件数で決まる(self):
        self.assertEqual(まとめ.高さ(台本), まとめ.HEAD_H + 3 * (まとめ.ITEM_H + まとめ.SOURCE_LINE) + まとめ.FOOT_BASE)

    def test_文字は書き換えずエスケープし_出典と注意を入れる(self):
        h = まとめ.ページ(台本)
        self.assertIn("福井の<br>カフェ&lt;3&gt;選", h)
        self.assertIn("営業時間は変わることがあります。", h)
        for i in range(3):
            self.assertIn(f"https://e/{i}", h)


if __name__ == "__main__":
    unittest.main()
