import os
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from threads_bot.poster import トピック
from threads_bot.queue import QueueItem

JST = ZoneInfo("Asia/Tokyo")


def 投稿(日: str, reply_to=None) -> QueueItem:
    return QueueItem(id="p", text="t", scheduled_at=datetime.fromisoformat(日 + "T12:00:00").replace(tzinfo=JST), reply_to=reply_to)


class トピックのテスト(unittest.TestCase):
    @mock.patch.dict(os.environ, {"THREADS_TOPIC": "福井", "THREADS_TOPIC_FROM": "2026-11-24"})
    def test_日ごとに交互(self):
        a, b = トピック(投稿("2026-11-24")), トピック(投稿("2026-11-25"))
        self.assertEqual({a, b}, {"福井", None})

    @mock.patch.dict(os.environ, {"THREADS_TOPIC": "福井", "THREADS_TOPIC_FROM": "2026-11-24"})
    def test_始める前と返信には付けない(self):
        self.assertIsNone(トピック(投稿("2026-11-22")))
        self.assertIsNone(トピック(投稿("2026-11-23")))
        self.assertIsNone(トピック(投稿("2026-11-24", reply_to="123")))
        self.assertIsNone(トピック(投稿("2026-11-25", reply_to="123")))

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_語が無ければ付けない(self):
        self.assertIsNone(トピック(投稿("2026-11-24")))


if __name__ == "__main__":
    unittest.main()
