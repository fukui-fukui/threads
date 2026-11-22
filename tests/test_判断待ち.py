import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("judge_for_test", ROOT / "scripts" / "判断待ち.py")
判断 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(判断)


def 地域を作る(d: Path, 投稿: list[dict]) -> None:
    (d / "neta").mkdir()
    (d / "posts").mkdir()
    (d / "state").mkdir()
    (d / "neta" / "ネタ帳.md").write_text("### 2026-10-19\n- なにか\n", encoding="utf-8")
    (d / "state" / "インスタ新着.json").write_text(
        json.dumps({"集めた日": "2026-10-19", "投稿": 投稿}, ensure_ascii=False), encoding="utf-8")


class インスタの引用(unittest.TestCase):
    def test_PRの投稿は引用できない(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            地域を作る(d, [
                {"アカウント": "Instagram @a_fukui", "日付": "2026-10-18", "本文": "a_fukui 新しいカフェ", "url": "https://www.instagram.com/p/1/"},
                {"アカウント": "Instagram @b_fukui", "日付": "2026-10-18", "本文": "b_fukui #PR 新商品", "url": "https://www.instagram.com/p/2/"},
            ])
            出 = 判断.インスタを読む(d, "ふくいおでかけ", date(2026, 10, 10))
            self.assertEqual([x["引用できる"] for x in 出], [True, False])
            self.assertEqual(出[0]["アカウント"], "a_fukui")

    def test_コメントがあるものだけ入れる(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            地域を作る(d, [])
            共通 = {"出どころ": "ふくいおでかけ", "種類": "インスタ（Meta）で読んだ新しい投稿", "答え": "引用",
                    "アカウント": "a_fukui", "url": "https://www.instagram.com/p/1/", "引用できる": True}
            済み = 判断.反映([
                {**共通, "id": "aaaaaaaa1", "一言": "秋の新作、気になります"},
                {**共通, "id": "bbbbbbbb2", "一言": ""},
                {**共通, "id": "cccccccc3", "一言": "これも", "引用できる": False},
            ], {"fukui": d})
            self.assertEqual(済み, ["aaaaaaaa1"])
            行 = [json.loads(l) for l in (d / "posts" / "queue.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(行), 1)
            self.assertIn("@a_fukui さんの投稿で紹介されていました", 行[0]["text"])
            self.assertTrue(行[0]["text"].startswith("秋の新作、気になります"))
            self.assertIn("https://www.instagram.com/p/1/", 行[0]["thread"][0])
            self.assertTrue(行[0]["approved_at"])


class AI活用の案(unittest.TestCase):
    def _yu(self, d: Path) -> None:
        (d / "posts").mkdir()
        (d / "scripts").mkdir()
        (d / "posts" / "queue.jsonl").write_text("# yu\n", encoding="utf-8")
        (d / "scripts" / "AI活用の投稿.py").write_text(
            "def 検査(文):\n    return ['金額'] if '$' in 文 else []\n", encoding="utf-8")
        行 = [{"id": "ai-A-1231-2030", "アカウント": "A", "scheduled_at": "2099-12-31T20:30:00+09:00", "text": "本文A", "材料": ["直した"]},
              {"id": "ai-B-1231-1210", "アカウント": "B", "scheduled_at": "2099-12-31T12:10:00+09:00", "text": "本文B"},
              {"id": "ai-A-0101-2030", "アカウント": "A", "scheduled_at": "2000-01-01T20:30:00+09:00", "text": "古い"}]
        (d / "posts" / "AI活用の案.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in 行), encoding="utf-8")

    def test_Aのまだ先の案だけ出す(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._yu(d)
            出 = 判断.AI活用の案を読む(d)
            self.assertEqual([x["id"] for x in 出], ["ai-A-1231-2030"])
            self.assertEqual(出[0]["返事"], "本文A")

    def test_出すで直した本文をqueueに入れ検査で止める(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self._yu(d)
            済み = 判断.AI活用を入れる([
                {"id": "ai-A-1231-2030", "出どころ": "yu（AI活用）", "種類": "AI活用の案", "答え": "出す", "返事": "直した本文"},
                {"id": "ai-A-1231-2031", "出どころ": "yu（AI活用）", "種類": "AI活用の案", "答え": "出す", "返事": "$5 かかった"},
            ], d)
            self.assertEqual(済み, ["ai-A-1231-2030"])
            行 = [json.loads(l) for l in (d / "posts" / "queue.jsonl").read_text(encoding="utf-8").splitlines() if l.startswith("{")]
            self.assertEqual(行[0]["id"], "p-ai-A-1231-2030")
            self.assertEqual(行[0]["text"], "直した本文")
            self.assertEqual(判断.AI活用の案を読む(d), [])


if __name__ == "__main__":
    unittest.main()
