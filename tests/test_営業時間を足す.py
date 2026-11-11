import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("営業時間を足す", Path(__file__).resolve().parents[1] / "scripts" / "営業時間を足す.py")
営業時間を足す = importlib.util.module_from_spec(spec)
spec.loader.exec_module(営業時間を足す)

# 2026-11-11 運用・ぎふあいち：水嶺湖音楽祭。番号付きの欄（4.入場料）を拾えず、下の合唱フェスティバルの欄をとっていた
ページ = """
 水嶺湖音楽祭2026 ミュージックフェスティバル
 1.とき 11月29日（日）13時00分〜16時00分（予定）
 2.ところ 日本昭和音楽村 江口夜詩記念館 水嶺湖ホール
 3.内容 「Bから始まる物語」
 4.入場料 無料 ※要申込（未就学児入場可）
 5.申 込 10月15日午前9時より、下記の申込フォームまたはお電話にてお申し込みください。
 ミュージックフェスティバルの申し込みはこちら
 合唱フェスティバル
 とき 12月6日（日）13時00分～16時00分
 入場料 無料 ※申込不要（未就学児入場不可）
"""


class 番号付きの欄(unittest.TestCase):
    def test_番号付きの入場料をとる(self):
        self.assertEqual(営業時間を足す.催しの欄(ページ, "ミュージックフェスティバル"), "料金: 無料 ※要申込（未就学児入場可）")

    def test_下の別の催しは別の欄(self):
        self.assertEqual(営業時間を足す.催しの欄(ページ, "合唱フェスティバル"), "料金: 無料 ※申込不要（未就学児入場不可）")


if __name__ == "__main__":
    unittest.main()
