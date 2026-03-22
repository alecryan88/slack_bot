from slack_bolt import App
from .summary_function import ack_summary, handle_summary_function_callback


def register(app: App):
    app.function("summary_function")(ack=ack_summary, lazy=[handle_summary_function_callback])
