import importlib.util
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compose  # noqa: E402

spec = importlib.util.spec_from_file_location("judge_for_waku", ROOT / "scripts" / "判断待ち.py")
判断 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(判断)
JST = ZoneInfo("Asia/Tokyo")


class 返事の間隔(unittest.TestCase):
    def test_1時間に3本まで20分あける(self):
        今 = datetime(2026, 11, 24, 4, 30, tzinfo=JST)
        時刻 = [datetime.fromisoformat(判断.返事の時刻(今, i)) for i in range(7)]
        for a, b in zip(時刻, 時刻[1:]):
            self.assertGreaterEqual(b - a, timedelta(minutes=20))
        for t in 時刻:
            self.assertIn(t.minute, (10, 30, 50))
            self.assertLessEqual(sum(1 for u in 時刻 if u.hour == t.hour and u.date() == t.date()), 3)


class 問いの題材(unittest.TestCase):
    def setUp(self):
        self._前 = (compose.地域.地域, compose.問いの時たち)
        self.addCleanup(self._戻す)

    def _戻す(self):
        compose.地域.地域, compose.問いの時たち = self._前

    def test_問いの枠でない時刻には付けない(self):
        compose.地域.地域 = {**self._前[0], "使う": {"問いの曜日配り": True}, "問いの曜日配りの時": 21}
        compose.問いの時たち = [14]
        self.assertEqual(compose.問いの題材の指示(date(2026, 11, 24)), [])

    def test_21時の問いに曜日で配る(self):
        compose.地域.地域 = {**self._前[0], "使う": {"問いの曜日配り": True}, "問いの曜日配りの時": 21}
        compose.問いの時たち = [14, 21]
        self.assertIn("21:00 の問いの題材：「土地の言葉", compose.問いの題材の指示(date(2026, 11, 27))[0])
        self.assertIn("21:00 の問いの題材：「暮らし", compose.問いの題材の指示(date(2026, 11, 26))[0])
        self.assertTrue(any("14:00 と 21:00 は別の題材" in l for l in compose.夜の問いの指示()))


if __name__ == "__main__":
    unittest.main()
