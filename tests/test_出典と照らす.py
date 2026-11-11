import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_terasu_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)

# 2026-11-11 統括・運用・ぎふあいち：水嶺湖音楽祭の申込・未就学児が逆、返信が「〜に出かけられる日です」だけ
材料 = ["- 11/29（日）大垣市の日本昭和音楽村で水嶺湖音楽祭2026の「ミュージックフェスティバル」"
        "（→ 西濃の音楽村で、晩秋から冬にかけて音楽祭が続く） ［料金: 無料 ※要申込（未就学児入場可）（https://example.jp/a）］"]


class 逆の言葉(unittest.TestCase):
    def test_申込と未就学児が逆なら止める(self):
        self.assertIsNotNone(compose.材料と逆の言葉("無料・申込不要です（未就学児は入場不可）", 材料))

    def test_同じなら通す(self):
        self.assertIsNone(compose.材料と逆の言葉("入場は無料で、申し込みが必要です（未就学児も入場できます）", 材料))

    def test_材料が無ければ見ない(self):
        self.assertIsNone(compose.材料と逆の言葉("申込不要です", []))

    def test_無料と書いて材料は金額だけ(self):
        self.assertIsNotNone(compose.材料と逆の言葉("入場無料です", ["- 「◯◯展」 ［料金: 一般 800円（https://example.jp/b）］"]))

    def test_材料の行は名前で探す(self):
        neta = "### 11/10\n" + 材料[0] + "\n- ほかの行「別の催し」\n"
        self.assertEqual(compose.材料の行たち({"ミュージックフェスティバル"}, neta), (材料, True))

    def test_出典のURLで先に探す(self):
        neta = "- 「クリスマスマーケット」A市 ［料金: 500円（https://a.example/x）］\n- 「クリスマスマーケット」B市 ［料金: 無料（https://b.example/y）］\n"
        行, 一つ = compose.材料の行たち({"クリスマスマーケット"}, neta, {"https://b.example/y?utm=1"})
        self.assertEqual((len(行), 一つ), (1, True))
        self.assertIn("B市", 行[0])

    def test_名前で2つの催しがまざれば1つとみない(self):
        neta = "- 「クリスマスマーケット」A市 ［料金: 500円（https://a.example/x）］\n- 「クリスマスマーケット」B市 ［料金: 無料（https://b.example/y）］\n"
        行, 一つ = compose.材料の行たち({"クリスマスマーケット"}, neta)
        self.assertEqual((len(行), 一つ), (2, False))

    def test_駐車場無料では止めない(self):
        self.assertIsNone(compose.材料と逆の言葉("駐車場無料です", ["- 「◯◯展」 ［料金: 一般 800円（https://example.jp/b）］"]))


class 事実の無い返信(unittest.TestCase):
    def test_見立ての写しは外す(self):
        th = ["大垣｜水嶺湖音楽祭2026（11/29）\n西濃の音楽村で、晩秋から冬にかけて日曜の音楽祭が続きます。\n出典元：https://example.jp/a"]
        直, わけ = compose.事実の無い返信を直す(th, "11月29日（日）…13:00〜16:00で、入場は無料です。", 材料)
        self.assertIn("見立て", わけ)
        self.assertEqual(直, ["大垣｜水嶺湖音楽祭2026（11/29）\n出典元：https://example.jp/a"])

    def test_本文に無い欄は差しかえる(self):
        th = ["大垣｜水嶺湖音楽祭2026（11/29）\n西濃の音楽村で、音楽祭が続きます。\n出典元：https://example.jp/a"]
        直, わけ = compose.事実の無い返信を直す(th, "11月29日（日）、大垣市で音楽祭が開かれるそうです。", 材料)
        self.assertIn("差しかえ", わけ)
        self.assertEqual(直[0].split("\n")[1], "料金：無料 ※要申込（未就学児入場可）")

    def test_1つと言えなければ差しこまない(self):
        th = ["大垣｜水嶺湖音楽祭2026（11/29）\n西濃の音楽村で、音楽祭が続きます。\n出典元：https://example.jp/a"]
        直, わけ = compose.事実の無い返信を直す(th, "11月29日（日）、大垣市で音楽祭が開かれるそうです。", 材料, False)
        self.assertNotIn("料金", 直[0])

    def test_事実があればそのまま(self):
        th = ["津島｜Roots⁺（11/15）\n10時〜16時、入場無料。駐車場は1台500円です。\n出典元：https://example.jp/c"]
        self.assertEqual(compose.事実の無い返信を直す(th, "本文", 材料), (th, None))


if __name__ == "__main__":
    unittest.main()
