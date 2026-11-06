import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_shop_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class 新店の型のテスト(unittest.TestCase):
    """2026-10-24 代表「任せるからすぐに対処して」：新店の投稿の型と、検索語の分け方"""

    def test_検索語は催し_お店_施設の3つ(self):
        お店 = compose.検索語_お店
        self.assertTrue(compose.検索語あり(f"本文\n\n{お店}"))
        self.assertTrue(compose.検索語あり(f"本文\n\n{compose.検索語}"))
        self.assertEqual(compose.検索語を外す(f"本文\n\n{compose.検索語_おでかけ}"), "本文")

    def test_数字の書き出しの新店は気づく(self):
        t = f"鶏ガラ約10羽分の出汁。坂井市春江町に「越ノ龍」がオープンしました。\n\n{compose.検索語_お店}"
        if compose.検索語_お店 != compose.検索語:
            self.assertIn("店名", compose.新店の型の気づき(t))

    def test_型どおりの新店と催しは気づかない(self):
        t = f"坂井市春江町のラーメン店「越ノ龍」が10月1日にオープンしました。\n鶏ガラ約10羽分の出汁。\n\n{compose.検索語_お店}"
        self.assertIsNone(compose.新店の型の気づき(t))
        self.assertIsNone(compose.新店の型の気づき(f"10時から。オープンガーデンが開かれます。\n\n{compose.検索語}"))
    def test_型より前の新店の予備は使わない(self):
        古い = f"福井駅から徒歩7分。「御宿 野乃福井」がオープンしたそうです。\n\n{compose.検索語}"
        self.assertTrue(compose.型より前の新店(古い))
        新しい = f"福井市の宿「御宿 野乃福井」が10月1日にオープンしました。\n大浴場があります。\n\n{compose.検索語_おでかけ}"
        self.assertFalse(compose.型より前の新店(新しい))
        self.assertFalse(compose.型より前の新店(f"10時から。オープンガーデンが開かれます。\n\n{compose.検索語}"))
    def test_新店の直しを見つける(self):
        if compose.検索語_お店 == compose.検索語:
            return
        g = compose.検索語_お店
        # 10/26 ぶん：言い切っていない・数字の書き出し・催しの検索語のまま
        self.assertIn("そうです", compose.新店の直し(f"福井市の天ぷら店「たかさか」ができたそうです。\n\n{g}"))
        self.assertIn("名前", compose.新店の直し(f"高さ約6mの立体迷路。越前市に「らくまるパーク」がオープンしました。\n\n{compose.検索語_おでかけ}"))
        self.assertIn("検索語", compose.新店の直し(f"福井市に天ぷら店「たかさか」がオープンしました。\n\n{compose.検索語}"))
        self.assertIsNone(compose.新店の直し(f"福井市の天ぷら店「たかさか」が10月1日にオープンしました。\n\n{g}"))
        # 読む人への問いかけは見ない（10/26 3県とも14:00が毎回作り直しになった）
        self.assertIsNone(compose.新店の直し(f"秋の夜、体が温まるものを1つだけ食べるなら、何にしますか？\n\n・打ち豆汁\n・ソースカツ丼\n\n{g}"))
        # 催しの投稿は見ない
        self.assertIsNone(compose.新店の直し(f"10月31日、勝山市で「ダイナソーフェス」が開かれるそうです。\n\n{compose.検索語}"))


if __name__ == "__main__":
    unittest.main()


class OpenLineTest(unittest.TestCase):
    def test_open_date_in_first_line(self):
        # 2026-11-03 代表「新店投稿は日時と『オープン』を一行目に入れる」
        古い = f"福井市のカフェ「テスト」。\n11月7日にオープンします。\n\n{compose.検索語_お店}"
        self.assertIn("1行目", compose.オープンの頭の直し(古い))
        self.assertIsNone(compose.オープンの頭の直し(f"11月7日（土）10時オープン、福井市のカフェ「テスト」。\n2行目。\n\nオープンおめでとうございます。"))
        self.assertIsNone(compose.オープンの頭の直し(f"10月31日（金）にオープンした、金沢市のコーヒーの店「テスト」。\n\nオープンおめでとうございます。"))
        後 = f"福井市のカフェ「テスト」。\n10月31日にオープンしました。\n\nオープンおめでとうございます。"
        self.assertIsNotNone(compose.オープンの頭の直し(後))
        # 1か月より前に開いた店のふつうの紹介は見ない
        self.assertIsNone(compose.オープンの頭の直し("福井市のカフェ「テスト」は2019年にオープンしました。"))


class CongratsTest(unittest.TestCase):
    # 2026-11-03 代表「おめでとうは、オープン日が明らかで、オープン日から前後10日以内の場合のみ」
    def test_within_10_days(self):
        from datetime import date
        t = "10月31日（金）にオープンした、金沢市のコーヒーの店「テスト」。\n看板はラテです。\n\nオープンおめでとうございます。"
        self.assertEqual(compose.おめでとうを確かめる(t, date(2026, 11, 5))[0], t)
        新, わけ = compose.おめでとうを確かめる(t, date(2026, 11, 20))
        self.assertIsNotNone(わけ)
        self.assertNotIn("おめでとう", 新)
        self.assertTrue(新.endswith("看板はラテです。"))
        # これから開く店（10日前まで）
        先 = "11月20日（金）10時オープン、福井市のカフェ「テスト」。\n\nオープンおめでとうございます。"
        self.assertEqual(compose.おめでとうを確かめる(先, date(2026, 11, 12))[0], 先)
        self.assertNotIn("おめでとう", compose.おめでとうを確かめる(先, date(2026, 11, 5))[0])
        # オープン日が無い・あいまい
        self.assertNotIn("おめでとう", compose.おめでとうを確かめる("12月中旬、「テスト」が移転オープンします。オープン、おめでとうございます。", date(2026, 11, 5))[0])
        # 年をまたぐ
        self.assertEqual(compose.オープン日("12月28日にオープンした、福井市の店「テスト」。", date(2027, 1, 3)), date(2026, 12, 28))


class OldEventTest(unittest.TestCase):
    # 2026-11-04 代表「4ヶ月前のイベントは出さない」
    def test_old_event(self):
        from datetime import date
        d = date(2026, 11, 4)
        self.assertIsNotNone(compose.古い催し("7月3日から、満天NAGOYAで「テスト」が上映されています。", d))
        self.assertIsNone(compose.古い催し("10月20日から、「テスト展」が開かれています。", d))
        self.assertIsNone(compose.古い催し("9月1日から11月9日まで開かれている「テスト展」が、まもなく終わります。", d))
        self.assertIsNotNone(compose.古い催し("9月1日から12月20日まで開かれている「テスト展」。", d))
        self.assertIsNone(compose.古い催し("11月20日から「テスト」が始まります。", d))
        self.assertIsNone(compose.古い催し("7月3日にオープンした、福井市の店「テスト」。", d))


class OldShopTest(unittest.TestCase):
    # 2026-11-04 代表「A」：オープンから30日をこえたお店は、「オープン」の言葉を使わず、ふつうのお店の紹介に
    def test_old_shop(self):
        from datetime import date
        t = "10月10日（土）にオープンした、金沢市東山の着物リメイク服の店「kimonodatta.」。\n\n町家を改装した店内です。\n\n石川おでかけ"
        新, わけ = compose.古い開店を直す(t, date(2026, 11, 20))
        self.assertIsNotNone(わけ)
        self.assertTrue(新.startswith("金沢市東山の着物リメイク服の店「kimonodatta.」。"))
        self.assertNotIn("オープン", 新)
        # 30日以内はそのまま
        self.assertEqual(compose.古い開店を直す(t, date(2026, 11, 5))[0], t)
        # 店名の文ごと消えるときは直せない
        self.assertIsNone(compose.古い開店を直す("9月1日、ついにオープン。\n\nパンの店です。", date(2026, 11, 20))[0])

    def test_old_shop_sentence(self):
        from datetime import date
        d = date(2026, 11, 5)
        self.assertTrue(compose.古い開店を直す("大野市西山に、サウナ「サウナばか」が2026年8月8日にオープンしました。\n\n貸切です。", d)[0]
                        .startswith("大野市西山に、サウナ「サウナばか」があります。"))
        self.assertTrue(compose.古い開店を直す("福井のカフェ「ha:on」は、2026年8月25日にオープンしました。\n\nスイーツです。", d)[0]
                        .startswith("福井のカフェ「ha:on」です。"))


class PromptCacheTest(unittest.TestCase):
    def test_cache_head(self):
        # 2026-11-06 統括：聞き直しで同じ指示を送り直すので、その部分をキャッシュする
        頭 = "決まり" * 2000
        compose.共通の頭 = 頭
        try:
            中 = compose.送る中身(頭 + "\n\n足りないのは 12:00 です。")
            self.assertEqual(中[0]["cache_control"], {"type": "ephemeral"})
            self.assertEqual(中[0]["text"], 頭)
            self.assertIn("12:00", 中[1]["text"])
            self.assertEqual(len(compose.送る中身(頭)), 1)
            self.assertEqual(compose.送る中身("別の指示"), "別の指示")
        finally:
            compose.共通の頭 = ""


class NotInSourceTest(unittest.TestCase):
    """2026-11-06 運用部・ぎふあいち：「時間・料金は出典に載っていません」が7本。出典には書いてあった。文ごと外す"""

    def test_removes_not_in_source_sentences(self):
        self.assertEqual(compose.載っていない文を外す("鶴舞公園の文化祭です。時間・料金は出典に載っていません。\n出典元：https://example.com/a"),
                         "鶴舞公園の文化祭です。\n出典元：https://example.com/a")
        self.assertEqual(compose.載っていない文を外す("点灯の時間や料金は、公式のお知らせで確かめてください。"), "")
        self.assertEqual(compose.載っていない文を外す("営業時間・定休日は出典に載っていないため、お出かけ前に確かめてください。\n場所は栄です。"), "場所は栄です。")

    def test_keeps_facts(self):
        for t in ("開館は10時〜17時、月曜休館です。", "出典元：https://example.com/a", "楽天トラベルの口コミは 4.6。"):
            self.assertEqual(compose.載っていない文を外す(t), t)

    def test_removes_go_check_sentences(self):
        # 2026-11-06 運用部・石川：「場所や営業時間は、記事でご確認ください」が4本
        self.assertEqual(compose.載っていない文を外す("一貫から頼めます。場所や営業時間は、記事でご確認ください。"), "一貫から頼めます。")
        self.assertEqual(compose.載っていない文を外す("メニューや営業時間は、お店のInstagramでご確認ください。"), "")
