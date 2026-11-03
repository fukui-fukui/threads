import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_omedetou_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class おめでとうのテスト(unittest.TestCase):
    """2026-11-03 代表：おめでとうは、オープンの日が明らかで前後10日以内のときだけ"""

    日 = date(2026, 11, 5)

    def test_10日以内は残す(self):
        t = "10月31日（金）にオープンした、岐阜市のカフェ「森」。\n看板はプリン。\nオープンおめでとうございます。"
        self.assertEqual(compose.おめでとうを確かめる(t, self.日), t)
        t2 = "11月14日（土）10時オープン、名古屋市のパン店「麦」。\nオープンおめでとうございます。"
        self.assertEqual(compose.おめでとうを確かめる(t2, self.日), t2)

    def test_10日をこえたら外す(self):
        t = "10月20日（月）にオープンした、岐阜市のカフェ「森」。\n看板はプリン。\nオープンおめでとうございます。\n\n#岐阜グルメ"
        出 = compose.おめでとうを確かめる(t, self.日)
        self.assertNotIn("おめでとう", 出)
        self.assertEqual(出, "10月20日（月）にオープンした、岐阜市のカフェ「森」。\n看板はプリン。\n\n#岐阜グルメ")

    def test_日が無いときは外す(self):
        t = "11月上旬にオープンした、岐阜市のカフェ「森」。看板はプリン。オープンおめでとうございます。"
        self.assertEqual(compose.おめでとうを確かめる(t, self.日), "11月上旬にオープンした、岐阜市のカフェ「森」。看板はプリン。")

    def test_年をまたぐ(self):
        t = "12月28日にオープンした店「森」。\nオープンおめでとうございます。"
        self.assertEqual(compose.おめでとうを確かめる(t, date(2027, 1, 3)), t)

    def test_おめでとうが無ければそのまま(self):
        t = "岐阜市のカフェ「森」。"
        self.assertEqual(compose.おめでとうを確かめる(t, self.日), t)


if __name__ == "__main__":
    unittest.main()
