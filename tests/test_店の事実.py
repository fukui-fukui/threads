import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compose_for_facts_test", ROOT / "scripts" / "compose.py")
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class ShopFactsTest(unittest.TestCase):
    # 2026-11-08 運用部・石川：「営業時間や定休日は、お店のInstagramで確かめて」の文で、Instagram だけの予備が通った
    def test_prompt_to_check_is_not_a_fact(self):
        t = "10月28日（水）にオープンした、金沢市横川の杏仁豆腐の店「杏仁豆腐TOKYO 金沢店」。\n営業時間や定休日は、お店のInstagramで確かめてから出かけるのがよさそうです。"
        self.assertFalse(compose.店の事実がある(t))

    def test_facts(self):
        self.assertTrue(compose.店の事実がある("営業は11:00〜18:00です。"))
        self.assertTrue(compose.店の事実がある("定休日は月曜です。"))
        self.assertTrue(compose.店の事実がある("金沢市野町2-3-4にあります。"))


if __name__ == "__main__":
    unittest.main()
