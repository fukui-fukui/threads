import importlib.util
import unittest
from datetime import date
from pathlib import Path

_path = Path(__file__).resolve().parent.parent / "scripts" / "おでかけ.py"
_spec = importlib.util.spec_from_file_location("odekake", _path)
odekake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(odekake)

BASE = date(2026, 9, 30)

NETA = """# ネタ帳

## 書き足す場所

### 2026-09-30

- 10/3-4 坂井市ゆりの里公園で「さかい米フェス2026」開催（→ 新米の2日間）
- 福井市に「テスト店」が2026年6月13日オープン（→ 新しい店）

<details><summary>出典</summary>

- https://example.com/a
- https://example.com/b

</details>

### 2026-09-29

- 10/3-4 坂井市ゆりの里公園で「さかい米フェス2026」開催（→ 古いほう）
- 日付のない話題（→ ひとこと）

## 書き方のヒント

- ここは読まない
"""


class ParseDatesTest(unittest.TestCase):
    def test_range_in_same_month(self):
        self.assertEqual(odekake.parse_dates("10/3-4 開催", BASE), (date(2026, 10, 3), date(2026, 10, 4)))

    def test_range_across_months(self):
        self.assertEqual(odekake.parse_dates("9/26-10/12 展示", BASE), (date(2026, 9, 26), date(2026, 10, 12)))

    def test_range_with_weekday_and_wave_dash(self):
        self.assertEqual(odekake.parse_dates("開催中（9/10〜11/3）", BASE), (date(2026, 9, 10), date(2026, 11, 3)))

    def test_listed_dates_become_span(self):
        self.assertEqual(odekake.parse_dates("9/25・10/2・10/30に実施", BASE), (date(2026, 9, 25), date(2026, 10, 30)))

    def test_single_with_weekday_and_time(self):
        self.assertEqual(odekake.parse_dates("10/25(日)10時〜15時30分 そばまつり", BASE), (date(2026, 10, 25), date(2026, 10, 25)))

    def test_japanese_date_with_year(self):
        self.assertEqual(odekake.parse_dates("2026年5月1日オープン", BASE), (date(2026, 5, 1), date(2026, 5, 1)))

    def test_january_written_in_autumn_is_next_year(self):
        self.assertEqual(odekake.parse_dates("1/10 開催", BASE)[0], date(2027, 1, 10))

    def test_no_date(self):
        self.assertEqual(odekake.parse_dates("参加者募集中", BASE), (None, None))


class GuessTest(unittest.TestCase):
    def test_area_uses_earliest_place(self):
        self.assertEqual(odekake.guess_area("あわら市温泉の店。三国産海鮮を使う"), "あわら市")

    def test_area_prefers_longer_name(self):
        self.assertEqual(odekake.guess_area("南越前町で開催"), "南越前町")

    def test_kind(self):
        self.assertEqual(odekake.guess_kind("福井市に店がオープン"), "スポット")
        self.assertEqual(odekake.guess_kind("10/3 まつり開催"), "催し")


class BuildTest(unittest.TestCase):
    def test_build(self):
        data = odekake.build(NETA)
        self.assertEqual(data["updated"], "2026-09-30")
        texts = [it["text"] for it in data["items"]]
        self.assertEqual(len(texts), 3)  # 重複は新しいほうだけ、ヒント欄は読まない
        fes = data["items"][0]
        self.assertEqual(fes["note"], "新米の2日間")
        self.assertEqual(fes["source"], "https://example.com/a")
        self.assertEqual((fes["area"], fes["region"], fes["kind"]), ("坂井市", "嶺北", "催し"))
        shop = data["items"][1]
        self.assertEqual((shop["kind"], shop["start"]), ("スポット", "2026-06-13"))

    def test_sources_not_paired_when_counts_differ(self):
        data = odekake.build(NETA)
        topic = [it for it in data["items"] if it["text"].startswith("日付のない")][0]
        self.assertIsNone(topic["source"])
        self.assertIsNone(topic["start"])


if __name__ == "__main__":
    unittest.main()
