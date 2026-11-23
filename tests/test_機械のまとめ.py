import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_kikai_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


def 催し(名, area, start, end, url, 前=""):
    return {"text": f"{前}{start[5:].replace('-', '/')}〜 {area}で「{名}」。", "kind": "催し", "area": area,
            "start": start, "end": end, "source": url}


class 機械のまとめ(unittest.TestCase):
    def setUp(self):
        self.元 = os.getcwd()
        self.dir = tempfile.TemporaryDirectory()
        os.chdir(self.dir.name)
        os.makedirs("docs")
        items = [
            催し("Aまつり", "福井市", "2026-11-01", "2026-11-30", "https://a.example/1"),
            催し("B展", "坂井市", "2026-10-01", "2026-11-30", "https://b.example/1"),
            {"text": "11/30 越前市で「C市」。", "kind": "催し", "area": "越前市", "start": "2026-11-30", "end": "2026-11-30", "source": "https://c.example/1"},
            # 終わりの日が分からない行（「から」）は、今日で終わるとは言わない
            {"text": "11/30（月）から敦賀市で「Dイルミ」。", "kind": "催し", "area": "敦賀市", "start": "2026-11-30", "end": "2026-11-30", "source": "https://d.example/1"},
            # 月曜休館の会場は、月曜の今日かぎりに入れない
            {"text": "10/1〜11/30 小浜市で「E展」。月曜休館", "kind": "催し", "area": "小浜市", "start": "2026-10-01", "end": "2026-11-30", "source": "https://e.example/1"},
            # 同じ市は1つだけ
            催し("F祭", "福井市", "2026-11-30", "2026-11-30", "https://f.example/1"),
            催し("G展", "大野市", "2026-09-01", "2026-11-30", "https://g.example/1"),
        ]
        Path("docs/data.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        os.chdir(self.元)
        self.dir.cleanup()

    def test_今日かぎりはデータの会期と出典だけで並べる(self):
        e = compose.機械のまとめ(date(2026, 11, 30), 6, None, set())
        self.assertIsNotNone(e)
        本文 = e["text"]
        self.assertIn("今日かぎりの催し4つ", 本文)
        for 名 in ("C市", "Aまつり", "B展", "G展"):
            self.assertIn(名, 本文)
        for 名 in ("Dイルミ", "E展", "F祭"):
            self.assertNotIn(名, 本文)
        self.assertEqual(len(e["thread"]), 4)
        self.assertTrue(all("出典元：https://" in t for t in e["thread"]))
        self.assertTrue(本文.endswith(compose.検索語))

    def test_今日で終わるものが無ければ作らない(self):
        self.assertIsNone(compose.機械のまとめ(date(2026, 11, 25), 6, None, set()))

    def test_7日以内に出した名前は入れない(self):
        e = compose.機械のまとめ(date(2026, 11, 30), 6, {"C市": ("2026-11-27", 12)}, set())
        self.assertNotIn("C市", e["text"])

    def test_一覧サイトだけの出典は入れない(self):
        items = json.loads(Path("docs/data.json").read_text(encoding="utf-8"))["items"]
        items[0]["source"] = "https://www.walkerplus.com/event/x"
        Path("docs/data.json").write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
        e = compose.機械のまとめ(date(2026, 11, 30), 6, None, set())
        self.assertNotIn("Aまつり", e["text"])

    def test_同じ日に使った出典は入れない(self):
        e = compose.機械のまとめ(date(2026, 11, 30), 6, None, {"https://a.example/1"})
        self.assertNotIn("Aまつり", e["text"])


if __name__ == "__main__":
    unittest.main()
