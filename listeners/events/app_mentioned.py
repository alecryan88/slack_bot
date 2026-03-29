from logging import Logger

from slack_sdk import WebClient

from ai import get_response
from ..utils.constants import DEFAULT_LOADING_TEXT, MENTION_WITHOUT_TEXT
from ..utils.parse_conversation import parse_conversation


def app_mentioned(ack, client: WebClient, event: dict, logger: Logger):
    ack()
    channel_id = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    raw_text = event.get("text", "")
    text = " ".join(w for w in raw_text.split() if not w.startswith("<@")).strip()

    thinking_ts = client.chat_postMessage(
        channel=channel_id,
        text=DEFAULT_LOADING_TEXT,
        thread_ts=thread_ts,
    )["ts"]

    try:
        replies = client.conversations_replies(
            channel=channel_id, ts=thread_ts, limit=50
        )["messages"]
        context_messages = [m for m in replies[:-1] if m.get("text") != DEFAULT_LOADING_TEXT]
        response = get_response(text, parse_conversation(context_messages)) if text else MENTION_WITHOUT_TEXT
        client.chat_update(channel=channel_id, ts=thinking_ts, text=response)

    except Exception as e:
        logger.error(e)
        client.chat_update(channel=channel_id, ts=thinking_ts, text=f"Error: {e}")
