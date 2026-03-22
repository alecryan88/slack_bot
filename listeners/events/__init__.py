from slack_bolt import App
from .app_home_opened import app_home_opened_callback
from .app_mentioned import ack_app_mentioned, app_mentioned_callback
from .app_messaged import ack_app_messaged, app_messaged_callback


def register(app: App):
    app.event("app_home_opened")(app_home_opened_callback)
    app.event("app_mention")(ack=ack_app_mentioned, lazy=[app_mentioned_callback])
    app.event("message")(ack=ack_app_messaged, lazy=[app_messaged_callback])
