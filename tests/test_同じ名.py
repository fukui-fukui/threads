import importlib.util
import sys
import unittest
from datetime import date
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

    def test_返信の見出しの名も拾う(self):
        # 10/21 石川：「」の無い催しが、10/19 と 10/22 に出た
        前 = {"text": "兼六園の雪吊りは…", "thread": ["金沢｜兼六園雪吊り作業（11/1〜12月中旬）\n…\n出典元：https://a/"]}
        後 = {"text": "【石川の雪吊り 2026】…", "thread": ["金沢｜兼六園雪吊り作業（11/1〜）\n…\n出典元：https://b/"]}
        self.assertIn("兼六園雪吊り作業", compose.名前たち(前))
        self.assertTrue(compose.名前たち(前) & compose.名前たち(後))
        self.assertIn("金沢城公園・玉泉院丸庭園ライトアップ",
                      compose.名前たち({"thread": ["金沢｜金沢城公園・玉泉院丸庭園ライトアップ\n和楽器の音…"]}))

    def test_7日以内の見出しの名で止める(self):
        前 = {"id": "a", "scheduled_at": "2026-10-19T21:00:00+09:00", "text": "夜のライトアップ",
              "thread": ["金沢｜金沢城公園・玉泉院丸庭園ライトアップ\n…"]}
        名記 = compose.名の記録([前], date(2026, 10, 22))
        後 = {"text": "庭を見たあと…", "thread": ["金沢｜金沢城公園・玉泉院丸庭園ライトアップ\n最終入園は20:45"]}
        if compose.同じ名を見る:
            self.assertIn("7日あける", compose.名で止める理由(後, 名記))

    def test_朝のまとめの見出しは数えない(self):
        朝 = {"id": "m", "scheduled_at": "2026-10-19T06:00:00+09:00", "text": "今日で終わる催し",
              "thread": ["金沢｜なにか展（10/19まで）\n…"]}
        self.assertNotIn("なにか展", compose.名の記録([朝], date(2026, 10, 22)))

    def test_先の日に手で入れた名も避ける(self):
        # 10/23 運用部・福井：先の日に手で入れた店を、その晩の作成がネタ帳から先に使った
        先 = {"id": "h", "scheduled_at": "2026-10-24T09:00:00+09:00", "text": "「越ノ龍」が新しくオープン"}
        名記 = compose.名の記録([先], date(2026, 10, 23))
        self.assertIn("越ノ龍", 名記)
        if compose.同じ名を見る:
            self.assertIn("7日あける", compose.名で止める理由({"text": "「越ノ龍」の話"}, 名記))
        # 8日より先と、対象日そのもの（同じ日の重なりは別に見ている）は入れない
        self.assertNotIn("越ノ龍", compose.名の記録([先], date(2026, 10, 16)))
        self.assertNotIn("越ノ龍", compose.名の記録([先], date(2026, 10, 24)))
    def test_並べる投稿から7日以内の名の行を外す(self):
        # 10/24 運用部・石川：10/22 に出したナイトミュージアムが 10/25 6:00 の並べる投稿に入っていた
        名記 = {"ナイトミュージアム": ("2026-10-22", 19)}
        t = "今日で終わる催し3つ\n\n①「ナイトミュージアム」\n金沢市\n②「秋の茶会」\n小松市\n③「菊花展」\n白山市\n\n石川イベント"
        新, 外した = compose.並べる投稿から外す(t, 名記)
        self.assertEqual([n for n, _ in 外した], ["ナイトミュージアム"])
        self.assertNotIn("ナイトミュージアム", 新)
        self.assertIn("①「秋の茶会」", 新)
        self.assertIn("②「菊花展」", 新)
        self.assertTrue(新.endswith("石川イベント"))
        # 外すと1行しか残らないときは外さない
        t2 = "①「ナイトミュージアム」\n②「秋の茶会」"
        self.assertEqual(compose.並べる投稿から外す(t2, 名記), (t2, []))


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
