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
