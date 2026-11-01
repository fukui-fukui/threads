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
    def test_three_kinds(self):
        # 2026-11-01 代表「1件をしっかりと紹介する投稿も」：催し × 宿 → 宿◯選 → 宿1軒 の3日で回す
        self.assertEqual(宿.十五時の型(date(2026, 11, 2)), "一軒")
        self.assertEqual(宿.十五時の型(date(2026, 11, 3)), "催し")
        self.assertEqual(宿.十五時の型(date(2026, 11, 4)), "まとめ")
        self.assertTrue(宿.まとめの日(date(2026, 11, 2)))
        self.assertFalse(宿.まとめの日(date(2026, 11, 3)))
        self.assertTrue(宿.まとめの日(date(2026, 11, 4)))

    def test_single_post(self):
        h = {"番号": 1, "名": "テストホテル", "エリア": "福井市", "住所": f"{宿.県}福井市中央1", "url": "https://example.com/1",
             "最安": 5390, "調べた日": "2026-10-26", "評価": 4.25, "レビュー数": 1234, "最寄駅": "福井",
             "駐車場": "有り 50台 無料", "朝食の場所": ["レストラン", "レストラン"],
             "風呂": [], "館内設備": ["大浴場", "サウナ"], "部屋の備品": []}
        元 = 宿.短縮を読む
        宿.短縮を読む = lambda: {}
        try:
            投稿 = 宿まとめ.一軒を組み立てる(date(2026, 11, 2), [h], 15)
        finally:
            宿.短縮を読む = 元
        self.assertIsNotNone(投稿)
        self.assertIn("最安料金は 5,390円〜（10/26時点）", 投稿["text"])
        self.assertNotIn("1名", 投稿["text"])
        self.assertNotIn("http", 投稿["text"])
        返信 = 投稿["thread"][0]
        self.assertTrue(返信.startswith("【PR】"))
        self.assertIn("※料金・プラン内容は宿泊日によって変動します", 返信)
        self.assertIn("｜朝食：レストラン", 返信)
        self.assertEqual(len(投稿["thread_links"]), 1)
        # 14日以内に出した宿は選ばない
        self.assertIsNone(宿まとめ.一軒を組み立てる(date(2026, 11, 2), [h], 15, {"テストホテル"}))

    def test_refresh_price(self):
        import io, json as _json, os, urllib.request
        h = {"番号": 12543, "名": "テストホテル", "最安": 17500, "調べた日": "2026-10-26"}
        元の環境 = {k: os.environ.pop(k, None) for k in ("RAKUTEN_APP_ID", "RAKUTEN_ACCESS_KEY")}
        try:
            self.assertEqual(宿まとめ.最安を取り直す(h), h)  # 鍵が無ければそのまま
            os.environ["RAKUTEN_APP_ID"], os.environ["RAKUTEN_ACCESS_KEY"] = "x", "y"
            返事 = {"hotels": [{"hotel": [{"hotelBasicInfo": {"hotelNo": 12543, "hotelMinCharge": 16000}}]}]}
            元 = urllib.request.urlopen
            urllib.request.urlopen = lambda *a, **k: io.BytesIO(_json.dumps(返事).encode())
            try:
                新 = 宿まとめ.最安を取り直す(h)
            finally:
                urllib.request.urlopen = 元
            self.assertEqual(新["最安"], 16000)
            self.assertNotEqual(新["調べた日"], "2026-10-26")
        finally:
            for k, v in 元の環境.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_recent_includes_any_post(self):
        h = {"番号": 1, "名": "テストホテル"}
        すでに = [{"text": "催しの紹介", "thread": ["近くの宿：テストホテル"], "note": "催し × 宿", "scheduled_at": "2026-10-25T15:00:00+09:00"}]
        self.assertEqual(宿まとめ.直近に出した宿(すでに, date(2026, 11, 2), [h]), {"テストホテル"})

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
