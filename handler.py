import base64
import hashlib
import hmac
import json
import os
import time

import boto3

from llm import call_llm
from slack import build_messages, get_thread_history, react, reply

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")


def _verify_slack_signature(event, raw_body: str) -> bool:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    timestamp = headers.get("x-slack-request-timestamp", "")
    signature = headers.get("x-slack-signature", "")

    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False

    sig_basestring = f"v0:{timestamp}:{raw_body}"
    expected = "v0=" + hmac.new(
        SLACK_SIGNING_SECRET.encode(), sig_basestring.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# Lambda 1: called by API Gateway, acks Slack immediately
def ack_handler(event, context):
    print("EVENT:", json.dumps(event))

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")

    if not _verify_slack_signature(event, raw):
        return {"statusCode": 403, "body": json.dumps({"error": "invalid signature"})}

    body = json.loads(raw)

    if body.get("type") == "url_verification":
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"challenge": body["challenge"]}),
        }

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
                (event_type == "message" and not is_thread_reply)
                or event_type == "app_mention"
            )
        )

        if should_process:
            react(slack_event["channel"], slack_event["ts"])

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
