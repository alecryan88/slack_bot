from slack_bolt import App
from .app_mentioned import ack_app_mentioned, app_mentioned_callback


def register(app: App):
    app.event("app_mention")(ack=ack_app_mentioned, lazy=[app_mentioned_callback])
