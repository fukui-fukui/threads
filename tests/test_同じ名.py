import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_name_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class 同じ名のテスト(unittest.TestCase):
    def test_長い英字の催し名も名として拾う(self):
        # 10/17 石川：32字の催し名が拾えず、4日あけで同じ催しを2回出した
        e = {"text": "小松市のアル・プラザ小松で「BON BON OYATSU MARKET in KOMATSU」が開かれるそうです。"}
        self.assertIn("BON BON OYATSU MARKET in KOMATSU", compose.名前たち(e))

    def test_ふつうの名も拾う(self):
        self.assertIn("ダイナソーフェス", compose.名前たち({"text": "「ダイナソーフェス」を開催"}))


if __name__ == "__main__":
    unittest.main()


class サイトへの返信のテスト(unittest.TestCase):
    def test_金曜19時はトップ_月水6時は月のページ_ほかは無し(self):
        from datetime import date
        金 = compose.サイトへの返信(19, date(2026, 10, 23), "p-1")
        self.assertIn("utm_campaign=weekend&utm_content=p-1", 金)
        月 = compose.サイトへの返信(6, date(2026, 10, 26), "p-2")
        self.assertIn("utm_campaign=month&utm_content=p-2", 月)
        self.assertIsNone(compose.サイトへの返信(6, date(2026, 10, 27), "p-3"))
        self.assertIsNone(compose.サイトへの返信(12, date(2026, 10, 23), "p-4"))
