import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import importlib  # noqa: E402

m = importlib.import_module("AI無しのまとめ")
# ほかのテストが地域を入れ替えて おでかけ を読み直すので、読んだものを残さない
for _名 in ("AI無しのまとめ", "おでかけ", "地域"):
    sys.modules.pop(_名, None)


def 催し(名, 市, 始, 終, url="https://example.jp/x"):
    return {"text": f"{始}〜 {市}で「{名}」が開かれる（主催の公式 {url}）", "kind": "催し", "area": 市,
            "start": 始, "end": 終, "source": None}


class AI無しのまとめのテスト(unittest.TestCase):
    def test_今日で終わる(self):
        items = [催し("A展", "福井市", "2026-11-01", "2026-11-30"), 催し("B祭", "鯖江市", "2026-11-20", "2026-11-30"),
                 催し("C展", "小浜市", "2026-10-01", "2026-11-30"), 催し("D", "大野市", "2026-11-30", "2026-11-30"),
                 催し("E", "敦賀市", "2026-11-01", "2026-12-05")]
        x = m.今日で終わる(items, date(2026, 11, 30))
        self.assertIn("今日で終わる催し3つ", x["本文"])
        self.assertNotIn("D", x["本文"])  # 1日だけの催しは入れない
        self.assertTrue(all("出典元：https://example.jp/x" in r for r in x["返信"]))

    def test_一覧サイトだけの出典は使わない(self):
        items = [催し(n, c, "2026-11-01", "2026-11-30", "https://www.walkerplus.com/e") for n, c in
                 (("A", "福井市"), ("B", "鯖江市"), ("C", "小浜市"))]
        self.assertIsNone(m.今日で終わる(items, date(2026, 11, 30)))

    def test_3件に届かなければ作らない(self):
        self.assertIsNone(m.今日で終わる([催し("A", "福井市", "2026-11-01", "2026-11-30")], date(2026, 11, 30)))


if __name__ == "__main__":
    unittest.main()
