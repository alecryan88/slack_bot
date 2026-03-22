import os
import logging

from slack_bolt import App, BoltResponse
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

from listeners import register_listeners

logging.basicConfig(level=logging.DEBUG)

app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    process_before_response=True,
)


@app.middleware
def ignore_retries(logger, req, next):
    if req.headers.get("x-slack-retry-num"):
        logger.info("Ignoring Slack retry")
        return BoltResponse(status=200, body="")
    return next()


register_listeners(app)

slack_handler = SlackRequestHandler(app)


def handler(event, context):
    return slack_handler.handle(event, context)
