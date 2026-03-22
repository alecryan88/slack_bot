from logging import Logger
from slack_sdk import WebClient
from ai.providers import MODEL


def app_home_opened_callback(event: dict, logger: Logger, client: WebClient):
    if event["tab"] != "home":
        return

    try:
        client.views_publish(
            user_id=event["user"],
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "Welcome to Bolty's Home Page!",
                            "emoji": True,
                        },
                    },
                    {"type": "divider"},
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Model:* {MODEL}\n\nMention me in a channel or send me a DM to get started.",
                        },
                    },
                ],
            },
        )
    except Exception as e:
        logger.error(e)
