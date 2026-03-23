from ai.ai_constants import DM_SYSTEM_CONTENT
from ai.providers import get_provider_response
from logging import Logger
from slack_bolt import Say
from slack_sdk import WebClient
from ..listener_utils.listener_constants import DEFAULT_LOADING_TEXT
from ..listener_utils.parse_conversation import parse_conversation

"""
Handles the event when a direct message is sent to the bot, retrieves the conversation context,
and generates an AI response.
"""


def ack_app_messaged(ack, say, event):
    ack()
    if event.get("channel_type") == "im":
        say(text=DEFAULT_LOADING_TEXT, thread_ts=event.get("thread_ts"))


def app_messaged_callback(client: WebClient, event: dict, logger: Logger):
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts")
    user_id = event.get("user")
    text = event.get("text")
    thinking_ts = None

    try:
        if event.get("channel_type") == "im":
            conversation_context = ""

            if thread_ts:
                replies = client.conversations_replies(
                    channel=channel_id, limit=50, ts=thread_ts
                )["messages"]
                thinking_ts = next(
                    (m["ts"] for m in reversed(replies) if m.get("text") == DEFAULT_LOADING_TEXT),
                    None,
                )
                context_messages = [m for m in replies[:-1] if m.get("text") != DEFAULT_LOADING_TEXT]
                conversation_context = parse_conversation(context_messages)
            else:
                # No thread yet — find the "Thinking..." message in the DM channel
                history = client.conversations_history(channel=channel_id, limit=5)["messages"]
                thinking_ts = next(
                    (m["ts"] for m in history if m.get("text") == DEFAULT_LOADING_TEXT),
                    None,
                )

            response = get_provider_response(user_id, text, conversation_context, DM_SYSTEM_CONTENT)

            if thinking_ts:
                client.chat_update(channel=channel_id, ts=thinking_ts, text=response)
            else:
                client.chat_postMessage(channel=channel_id, text=response)

    except Exception as e:
        logger.error(e)
        if thinking_ts:
            client.chat_update(channel=channel_id, ts=thinking_ts, text=f"Error: {e}")
