import base64
import json
import os
import urllib.parse
import urllib.request

import boto3

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
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
    messages = [{"role": "system", "content": "You are a helpful assistant in a Slack thread."}]
    for msg in thread_messages:
        role = "assistant" if msg.get("user") == BOT_USER_ID else "user"
        messages.append({"role": role, "content": msg.get("text", "")})
    return messages


GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_github_repos",
            "description": "Search GitHub repositories by keyword",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query, e.g. 'fastapi python web framework'",
                    }
                },
                "required": ["query"],
            },
        },
    }
]


def search_github_repos(query: str) -> str:
    req = urllib.request.Request(
        "https://api.github.com/user/repos?per_page=100&sort=updated&affiliation=owner",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req) as resp:
        repos = json.loads(resp.read().decode())

    query_lower = query.lower()
    matches = [
        r for r in repos
        if query_lower in r["name"].lower()
        or query_lower in (r["description"] or "").lower()
    ]

    if not matches:
        encoded = urllib.parse.quote(query)
        req = urllib.request.Request(
            f"https://api.github.com/search/repositories?q={encoded}&per_page=5&sort=stars",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
        matches_public = data.get("items", [])
        results = [f"- {r['full_name']} ⭐{r['stargazers_count']}: {r['description']} ({r['html_url']})" for r in matches_public]
        return "\n".join(results) if results else "No repositories found."

    results = [f"- {r['full_name']} {'🔒' if r['private'] else '🌐'}: {r['description']} ({r['html_url']})" for r in matches]
    return "\n".join(results)


def call_llm(messages: list) -> str:
    from openai import OpenAI
    client = OpenAI()

    while True:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        if response.choices[0].finish_reason == "tool_calls":
            messages.append(msg)
            for tool_call in msg.tool_calls:
                args = json.loads(tool_call.function.arguments)
                print(f"TOOL CALL: {tool_call.function.name}({args})")
                result = search_github_repos(args["query"])
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            return msg.content


# Lambda 1: called by API Gateway, acks Slack immediately
def ack_handler(event, context):
    print("EVENT:", json.dumps(event))

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    body = json.loads(raw)

    # Slack URL verification (one-time setup)
    if body.get("type") == "url_verification":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"challenge": body["challenge"]}),
        }

    # Ignore Slack retries — we already processed this event
    if event.get("headers", {}).get("x-slack-retry-num"):
        return {"statusCode": 200, "body": json.dumps({"ok": True})}

    if body.get("type") == "event_callback":
        slack_event = body.get("event", {})
        event_type = slack_event.get("type")
        is_thread_reply = slack_event.get("thread_ts") and slack_event.get("thread_ts") != slack_event.get("ts")

        should_process = (
            "text" in slack_event
            and not slack_event.get("bot_id")
            and (
                (event_type == "message" and not is_thread_reply)  # top-level message
                or event_type == "app_mention"                      # @mention anywhere (including threads)
            )
        )

        if should_process:
            reaction_payload = json.dumps({
                "channel": slack_event["channel"],
                "timestamp": slack_event["ts"],
                "name": "eyes",
            }).encode()
            req = urllib.request.Request(
                "https://slack.com/api/reactions.add",
                data=reaction_payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                },
            )
            with urllib.request.urlopen(req) as resp:
                print("REACTION:", resp.read().decode())

            # For thread replies use the thread root; for top-level messages the message itself becomes the thread root
            thread_ts = slack_event.get("thread_ts") or slack_event["ts"]

            sqs = boto3.client("sqs")
            sqs.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps({
                    "channel": slack_event["channel"],
                    "thread_ts": thread_ts,
                }),
            )

    return {"statusCode": 200, "body": json.dumps({"ok": True})}


# Lambda 2: triggered by SQS, fetches thread history, calls LLM and replies
def process_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        print("PROCESSING:", json.dumps(body))

        thread_messages = get_thread_history(body["channel"], body["thread_ts"])
        messages = build_messages(thread_messages)
        response = call_llm(messages)
        reply(body["channel"], body["thread_ts"], response)
