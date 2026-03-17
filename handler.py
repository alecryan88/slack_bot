import base64
import json
import os
import urllib.parse
import urllib.request

import boto3

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")


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

    results = []
    for repo in data.get("items", []):
        results.append(f"- {repo['full_name']} ⭐{repo['stargazers_count']}: {repo['description']} ({repo['html_url']})")
    return "\n".join(results) if results else "No repositories found."


def call_llm(text: str) -> str:
    from openai import OpenAI
    client = OpenAI()
    messages = [{"role": "user", "content": text}]

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

    # Handle message events
    if body.get("type") == "event_callback":
        slack_event = body.get("event", {})
        is_thread_reply = slack_event.get("thread_ts") and slack_event.get("thread_ts") != slack_event.get("ts")
        if (
            slack_event.get("type") == "message"
            and "text" in slack_event
            and not slack_event.get("bot_id")
            and not is_thread_reply
        ):
            # React with eyes to show the message is being processed
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

            sqs = boto3.client("sqs")
            sqs.send_message(
                QueueUrl=SQS_QUEUE_URL,
                MessageBody=json.dumps({
                    "text": slack_event["text"],
                    "channel": slack_event["channel"],
                    "thread_ts": slack_event["ts"],
                }),
            )

    return {"statusCode": 200, "body": json.dumps({"ok": True})}


# Lambda 2: triggered by SQS, calls LLM and replies
def process_handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        print("PROCESSING:", json.dumps(body))

        response = call_llm(body["text"])
        reply(body["channel"], body["thread_ts"], response)
