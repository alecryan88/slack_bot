from slack_bolt import App
from .ask_command import ack_ask, ask_callback


def register(app: App):
    app.command("/ask-bolty")(ack=ack_ask, lazy=[ask_callback])
