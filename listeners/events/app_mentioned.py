from ai.providers import get_provider_response
from logging import Logger
from slack_sdk import WebClient
from slack_bolt import Say
from ..listener_utils.listener_constants import (
    DEFAULT_LOADING_TEXT,
    MENTION_WITHOUT_TEXT,
)
from ..listener_utils.parse_conversation import parse_conversation

"""
Handles the event when the app is mentioned in a Slack channel, retrieves the conversation context,
and generates an AI response if text is provided, otherwise sends a default response
"""


def ack_app_mentioned(ack, say, event):
    ack()
    thread_ts = event.get("thread_ts") or event["ts"]
    say(text=DEFAULT_LOADING_TEXT, thread_ts=thread_ts)


def app_mentioned_callback(client: WebClient, event: dict, logger: Logger):
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts") or event["ts"]
    user_id = event.get("user")
    raw_text = event.get("text", "")
    text = " ".join(w for w in raw_text.split() if not w.startswith("<@")).strip()
    thinking_ts = None

    try:
        replies = client.conversations_replies(
            channel=channel_id, ts=thread_ts, limit=50
        )["messages"]

        # Find the "Thinking..." message posted by the ack to update it later
        thinking_ts = next(
            (m["ts"] for m in reversed(replies) if m.get("text") == DEFAULT_LOADING_TEXT),
            None,
        )

        # Build context excluding the "Thinking..." placeholder
        context_messages = [m for m in replies[:-1] if m.get("text") != DEFAULT_LOADING_TEXT]
        conversation_context = parse_conversation(context_messages)

        response = get_provider_response(user_id, text, conversation_context) if text else MENTION_WITHOUT_TEXT

        if thinking_ts:
            client.chat_update(channel=channel_id, ts=thinking_ts, text=response)
        else:
            client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=response)

    except Exception as e:
        logger.error(e)
        if thinking_ts:
            client.chat_update(channel=channel_id, ts=thinking_ts, text=f"Error: {e}")
