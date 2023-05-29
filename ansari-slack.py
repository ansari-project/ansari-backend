import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt import App
from flask import Flask, request

slack_client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
response = slack_client.auth_test()
print(response["user_id"])

app = App(token=os.environ["SLACK_BOT_TOKEN"])
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)
flask_app.run(port=3000)

# Decorator for handling direct bot message events
@app.event("message")
def handle_direct_message(event, say):
    if event.get("subtype") is None and event.get("channel_type") == "im":
        user_id = event["user"]
        text = event["text"]
        # Handle the direct message event here
        # For example, you can send a response using the `say` method
        say(f"Received direct message from user {user_id}: {text}")


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    """
    Route for handling Slack events.
    This function passes the incoming HTTP request to the SlackRequestHandler for processing.

    Returns:
        Response: The result of handling the request.
    """
    return handler.handle(request)