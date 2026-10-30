"""キューの項目を実際に Threads へ投稿する処理。"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .client import PostResult, ThreadsAPIError, ThreadsClient
from .config import Config
from .queue import QueueItem

logger = logging.getLogger(__name__)

# 自分のサイトへのリンクに、どの投稿から来たかの印（UTM）を付ける（2026-10-13 代表「つける」）。
# GA で utm_campaign（日付と時刻）・utm_content（投稿の id）ごとに見られる。
_自分のサイト = re.compile(r"https?://(?:odekake|ishikawa-odekake)\.fukui-fukui\.com[^\s）)」』、。]*")


def _印を付けたURL(url: str, item: QueueItem) -> str:
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    when = item.scheduled_at.strftime("%Y%m%d-%H") if item.scheduled_at else "nodate"
    q.update({"utm_source": "threads", "utm_medium": "social",
              "utm_campaign": f"{'reply' if item.reply_to else 'post'}-{when}", "utm_content": item.id})
    return urlunsplit(parts._replace(path=parts.path or "/", query=urlencode(q)))


def add_utm(text: str | None, item: QueueItem) -> str | None:
    if not text:
        return text
    return _自分のサイト.sub(lambda m: _印を付けたURL(m.group(0), item), text)


def publish_item(
    client: ThreadsClient,
    item: QueueItem,
    config: Config,
    *,
    dry_run: bool = False,
) -> PostResult | None:
    """1 件（連投がある場合はその一連）を投稿する。dry-run なら何も送らない。"""
    if dry_run:
        logger.info(
            "[dry-run] 投稿しません id=%s media_type=%s text=%r thread=%d件",
            item.id,
            item.media_type,
            item.text,
            len(item.thread),
        )
        return None

    creation_id = client.create_container(
        text=add_utm(item.text, item),
        media_type=item.media_type,
        image_url=item.image_url,
        video_url=item.video_url,
        link_attachment=add_utm(item.link_attachment, item),
        reply_control=item.reply_control,
        alt_text=item.alt_text,
        reply_to_id=item.reply_to,
    )
    _wait_for_container(client, creation_id, item.media_type, config)
    post_id = client.publish(creation_id)
    logger.info("投稿しました id=%s post_id=%s", item.id, post_id)

    # 連投は 1 件目への返信として順につなげる。
    # 本体はもう出ているので、ここで失敗しても投稿済みとして記録する（失敗扱いにすると、次の回にまた本体から出し直してしまう。
    # 2026-10-30 カフェ5選リール：返信が「HTTP 400 An unknown error」で落ち、10分ごとに本体が4回出た）
    try:
        _post_thread(client, item, config, post_id)
    except ThreadsAPIError as exc:
        logger.error("::error::本体は出ました（post_id=%s）が、連投の途中で失敗しました id=%s: %s。投稿済みとして記録します。返信は手で足してください", post_id, item.id, exc)

    return PostResult(
        creation_id=creation_id, post_id=post_id, permalink=client.permalink(post_id)
    )


def _post_thread(client: ThreadsClient, item: QueueItem, config: Config, post_id: str) -> None:
    reply_to = post_id
    for index, text in enumerate(item.thread, start=2):
        text = add_utm(text, item)
        links = item.thread_links
        link = add_utm(links[index - 2], item) if index - 2 < len(links) else None
        try:
            reply_container = client.create_container(
                text=text, reply_to_id=reply_to, link_attachment=link or None
            )
        except ThreadsAPIError:
            if not link:
                raise
            # カードが付けられなかったときは、URL を本文の末尾に書いて出す（返信が抜けないように）
            logger.warning("連投 %d 件目のリンクカードが付けられません。URL を本文に書いて出します", index)
            reply_container = client.create_container(text=f"{text}\n{link}", reply_to_id=reply_to)
        _wait_for_container(client, reply_container, "TEXT", config)
        reply_to = client.publish(reply_container)
        logger.info("連投 %d 件目を投稿しました post_id=%s", index, reply_to)


def _wait_for_container(
    client: ThreadsClient, container_id: str, media_type: str, config: Config
) -> None:
    if media_type == "TEXT":
        # テキストは即時に公開できるが、直後の publish が稀に失敗するため少し待つ
        client.sleep(config.publish_delay)
        return
    client.wait_until_ready(container_id, interval=config.media_publish_delay / 6)
