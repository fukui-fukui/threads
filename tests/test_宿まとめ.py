import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import 宿  # noqa: E402

spec = importlib.util.spec_from_file_location("宿まとめ", ROOT / "scripts" / "宿まとめの投稿.py")
宿まとめ = importlib.util.module_from_spec(spec)
spec.loader.exec_module(宿まとめ)


class RoundupTest(unittest.TestCase):
    def test_alternates_days(self):
        # 2026-10-12 代表「催し+宿と〇〇選を1日おきでいいですよ」。10/13 が宿◯選の日
        self.assertTrue(宿.まとめの日(date(2026, 10, 13)))
        self.assertFalse(宿.まとめの日(date(2026, 10, 14)))
        self.assertTrue(宿.まとめの日(date(2026, 10, 15)))

    def test_post_shape(self):
        宿たち = [
            {"番号": i, "名": f"宿{i}", "エリア": "福井市", "住所": f"{宿.県}福井市中央{i}", "url": f"https://example.com/{i}",
             "評価": 4.25, "レビュー数": 1234, "風呂": "", "館内設備": "", "部屋の備品": ""}
            for i in range(1, 8)
        ]
        元 = 宿.短縮を読む
        宿.短縮を読む = lambda: {}
        try:
            p = 宿まとめ.組み立てる(date(2026, 10, 13), 宿たち, 15)
        finally:
            宿.短縮を読む = 元
        self.assertIsNotNone(p)
        self.assertTrue(p["text"].startswith(f"【{宿.県名}】"))
        self.assertIn("選", p["text"].splitlines()[0])
        self.assertEqual(len(p["thread"]), len(p["thread_links"]))
        self.assertTrue(p["thread"][0].startswith("【PR】\n①"))
        self.assertIn("⭐口コミ 4.2（1,234件）", p["thread"][0])
        self.assertNotIn("http", "\n".join(p["thread"]))
        self.assertEqual(p["scheduled_at"], "2026-10-13T15:00:00+09:00")


if __name__ == "__main__":
    unittest.main()
