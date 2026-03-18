import json
import os
import urllib.request

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
BOT_USER_ID = os.environ.get("BOT_USER_ID")


def reply(channel: str, thread_ts: str, text: str):
    payload = json.dumps({
        "channel": channel,
        "thread_ts": thread_ts,
        "text": text,
    }).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        print("SLACK REPLY:", resp.read().decode())


def react(channel: str, ts: str, emoji: str = "eyes"):
    payload = json.dumps({
        "channel": channel,
        "timestamp": ts,
        "name": emoji,
    }).encode()
    req = urllib.request.Request(
        "https://slack.com/api/reactions.add",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        print("REACTION:", resp.read().decode())


def get_thread_history(channel: str, thread_ts: str) -> list:
    url = f"https://slack.com/api/conversations.replies?channel={channel}&ts={thread_ts}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    return data.get("messages", [])


def build_messages(thread_messages: list) -> list:
    messages = []
    for msg in thread_messages:
        role = "assistant" if msg.get("user") == BOT_USER_ID else "user"
        text = msg.get("text", "").strip()
        if not text:
            continue
        # Merge consecutive same-role messages to satisfy API alternation requirement
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + text
        else:
            messages.append({"role": role, "content": text})
    return messages
