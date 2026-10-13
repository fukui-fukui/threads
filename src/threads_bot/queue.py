"""投稿キュー（JSONL）の読み込みと、次に投稿すべき項目の選択。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .client import MAX_TEXT_LENGTH

VALID_REPLY_CONTROLS = {"everyone", "accounts_you_follow", "mentioned_only"}


class QueueError(Exception):
    """キューファイルの内容が不正。"""


@dataclass
class QueueItem:
    id: str
    text: str
    scheduled_at: datetime | None = None
    image_url: str | None = None
    video_url: str | None = None
    link_attachment: str | None = None
    reply_control: str | None = None
    alt_text: str | None = None
    # 連投（スレッド）。1 件目への返信として順に投稿される。
    thread: list[str] = field(default_factory=list)
    # 連投のそれぞれに付けるリンクカード（link_attachment）。thread と同じ順。無いものは None。
    # URL を本文に書かずにカードで見せるため（2026-10-12 代表「リンクURLを表示せず、カードで見せる」）
    thread_links: list[str | None] = field(default_factory=list)
    # 読者の返信への返事（2026-10-13 代表「進めてOK」）。入っていれば、1件目をこの投稿への返信として出す。
    # 代表が判断待ちダッシュボードで「出す」を押したものだけが、scripts/判断待ち.py からここに入る。
    reply_to: str | None = None
    # 代表が「出す」を押した時刻。reply_to のある返事は、これが無いと出さない（2026-10-13 エキマエ開発のすすめ）
    approved_at: str | None = None
    line_number: int = 0

    @property
    def media_type(self) -> str:
        if self.video_url:
            return "VIDEO"
        if self.image_url:
            return "IMAGE"
        return "TEXT"


def _parse_scheduled_at(raw: str, tz: ZoneInfo, *, where: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise QueueError(
            f"{where}: scheduled_at が ISO 8601 形式ではありません: {raw!r}"
        ) from exc
    # タイムゾーン省略時は設定のタイムゾーン（既定 Asia/Tokyo）とみなす
    return parsed.replace(tzinfo=tz) if parsed.tzinfo is None else parsed


def _parse_item(raw: dict, *, line_number: int, tz: ZoneInfo) -> QueueItem:
    where = f"{line_number} 行目"
    if not isinstance(raw, dict):
        raise QueueError(f"{where}: オブジェクトではありません")

    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise QueueError(f"{where}: text が空です")
    if len(text) > MAX_TEXT_LENGTH:
        raise QueueError(f"{where}: text が {MAX_TEXT_LENGTH} 文字を超えています ({len(text)} 文字)")

    thread = raw.get("thread") or []
    if not isinstance(thread, list) or any(not isinstance(t, str) or not t.strip() for t in thread):
        raise QueueError(f"{where}: thread は空でない文字列の配列にしてください")
    for index, part in enumerate(thread, start=2):
        if len(part) > MAX_TEXT_LENGTH:
            raise QueueError(
                f"{where}: thread の {index} 件目が {MAX_TEXT_LENGTH} 文字を超えています"
            )

    thread_links = raw.get("thread_links") or []
    if not isinstance(thread_links, list) or len(thread_links) > len(thread) or any(
        u is not None and (not isinstance(u, str) or not u.startswith(("http://", "https://")))
        for u in thread_links
    ):
        raise QueueError(
            f"{where}: thread_links は thread と同じ順の URL（無いものは null）の配列にしてください"
        )

    reply_to = raw.get("reply_to")
    if reply_to is not None and not (isinstance(reply_to, str) and reply_to.isdigit()):
        raise QueueError(f"{where}: reply_to は返事を付ける投稿の ID（数字の文字列）にしてください")

    reply_control = raw.get("reply_control")
    if reply_control is not None and reply_control not in VALID_REPLY_CONTROLS:
        raise QueueError(
            f"{where}: reply_control は {sorted(VALID_REPLY_CONTROLS)} のいずれかです"
        )

    if raw.get("image_url") and raw.get("video_url"):
        raise QueueError(f"{where}: image_url と video_url は同時に指定できません")

    scheduled_raw = raw.get("scheduled_at")
    scheduled_at = (
        _parse_scheduled_at(scheduled_raw, tz, where=where) if scheduled_raw else None
    )

    item_id = raw.get("id") or hashlib.sha1(text.encode()).hexdigest()[:12]
    return QueueItem(
        id=str(item_id),
        text=text,
        scheduled_at=scheduled_at,
        image_url=raw.get("image_url"),
        video_url=raw.get("video_url"),
        link_attachment=raw.get("link_attachment"),
        reply_control=reply_control,
        alt_text=raw.get("alt_text"),
        thread=list(thread),
        thread_links=list(thread_links),
        reply_to=reply_to,
        approved_at=raw.get("approved_at") or None,
        line_number=line_number,
    )


def load_queue(path: str | Path, *, timezone: str = "Asia/Tokyo") -> list[QueueItem]:
    """JSONL を読み込む。空行と `#` で始まる行はコメントとして無視する。"""
    file_path = Path(path)
    if not file_path.exists():
        raise QueueError(f"キューファイルが見つかりません: {file_path}")

    tz = ZoneInfo(timezone)
    items: list[QueueItem] = []
    seen: dict[str, int] = {}
    for line_number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise QueueError(f"{line_number} 行目: JSON として読めません: {exc}") from exc
        item = _parse_item(raw, line_number=line_number, tz=tz)
        if item.id in seen:
            raise QueueError(
                f"{line_number} 行目: id {item.id!r} が {seen[item.id]} 行目と重複しています"
            )
        seen[item.id] = line_number
        items.append(item)
    return items


def select_due(
    items: list[QueueItem],
    posted_ids: set[str],
    *,
    now: datetime,
    limit: int = 1,
) -> list[QueueItem]:
    """今回のランで投稿すべき項目を、予約時刻の早い順に返す。

    - 投稿済みの id は除外
    - scheduled_at が未来のもの、そもそも無いものは除外

    予約時刻のない項目は投稿されない。何度叩かれても予約時刻が来たものしか
    出ないので、起動の間隔を短くしても投稿が増えない。
    """
    return sorted(
        (
            item
            for item in items
            if item.id not in posted_ids
            and item.scheduled_at is not None
            and item.scheduled_at <= now
            # 読者の返信への返事は、代表が「出す」を押した印（approved_at）があるものだけ
            and (item.reply_to is None or bool(item.approved_at))
        ),
        key=lambda i: (i.scheduled_at, i.line_number),
    )[: max(limit, 0)]


def without_schedule(items: list[QueueItem], posted_ids: set[str]) -> list[QueueItem]:
    """未投稿なのに予約時刻がない項目。このままでは永久に投稿されない。"""
    return [
        item
        for item in items
        if item.id not in posted_ids and item.scheduled_at is None
    ]
