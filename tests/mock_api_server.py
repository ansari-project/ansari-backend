"""Run the API locally with every external service mocked except MongoDB.

Mocked:
    * Anthropic (Claude) - a fake model that streams back a description of what it received,
      e.g. how many images, their types and sizes, and any notes about earlier images.
      It never calls tools, so the search APIs (Kalemat, Vectara, quran.com, Usul) are never reached.
      With --real-claude, the real Claude API is used instead (needs ANTHROPIC_API_KEY in .env or the shell)
      and the search tools answer "unavailable", so Claude replies from its own knowledge.
    * Mailchimp (registration) and SendGrid (password reset) - logged instead of sent.
    * Sentry - disabled (DEPLOYMENT_TYPE=development).

Usage (from the repo root, with MongoDB running locally):
    uv run python tests/mock_api_server.py [--port 8000] [--real-claude]

Environment variables in .env (or the shell) still apply; required API keys get dummy defaults.
The database is `ansari_mock` (so your normal dev data is untouched); override it with MONGO_DB_NAME in the shell.
"""

import argparse
import base64
import os
import time
from types import SimpleNamespace

from dotenv import dotenv_values

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from a phone on your LAN")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--real-claude", action="store_true", help="call the real Claude API (search tools stay mocked)")
args = parser.parse_args()

# Dummy values for required settings; must be set before any `ansari` import reads the settings
for key in ("WHATSAPP_SERVICE_API_KEY", "OPENAI_API_KEY", "KALEMAT_API_KEY", "VECTARA_API_KEY", "QURAN_DOT_COM_API_KEY"):
    os.environ.setdefault(key, "mock")
if args.real_claude:
    # The Anthropic SDK reads the key from the process environment, not from .env
    os.environ.setdefault("ANTHROPIC_API_KEY", dotenv_values(".env").get("ANTHROPIC_API_KEY") or "")
    if not os.environ["ANTHROPIC_API_KEY"]:
        raise SystemExit("--real-claude needs ANTHROPIC_API_KEY in .env or the shell")
else:
    os.environ["ANTHROPIC_API_KEY"] = "mock"
os.environ["DEPLOYMENT_TYPE"] = "development"  # keeps Sentry off
# Placeholder in case .env has an empty SENTRY_DSN (which fails validation); never used in development
os.environ["SENTRY_DSN"] = "https://mock@localhost/0"
os.environ["DEV_MODE"] = "true"  # also allows the web app on http://localhost:8081 (CORS)
os.environ.setdefault("MONGO_DB_NAME", "ansari_mock")
os.makedirs("logs", exist_ok=True)

import anthropic  # noqa: E402
import uvicorn  # noqa: E402

# ---------------------------------------------------------------------------
# Fake Anthropic client
# ---------------------------------------------------------------------------


def _describe_request(params: dict) -> str:
    """Build the fake model's reply: a report of what the API call contained."""
    messages = params["messages"]
    last = messages[-1]
    content = last["content"] if isinstance(last["content"], list) else [{"type": "text", "text": last["content"]}]

    lines = ["**[Mock Claude]** Here is what I received for this turn:", ""]
    images = [b for b in content if b.get("type") == "image"]
    for i, block in enumerate(images, 1):
        size_kb = len(base64.b64decode(block["source"]["data"])) / 1024
        lines.append(f"- Image {i}: `{block['source']['media_type']}`, {size_kb:.0f} KB")
    if not images:
        lines.append("- No images")

    texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
    lines.append(f"- Text: {texts[0]!r}" if texts else "- No text")

    earlier_notes = sum(
        1
        for m in messages[:-1]
        if m["role"] == "user" and "The user attached" in str(m["content"]) and "no longer available" in str(m["content"])
    )
    lines.append(
        f"- Earlier messages: {len(messages) - 1}, of which {earlier_notes} mention an image that is no longer available"
    )
    lines += ["", f"Model: `{params['model']}`, system prompt: {len(params['system'][0]['text'])} chars."]
    return "\n".join(lines)


def _stream(text: str):
    """Yield chunks shaped like Anthropic's streaming events, as consumed by AnsariClaude.process_one_round."""
    yield SimpleNamespace(type="message_start")
    yield SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="text"))
    for word in text.split(" "):
        time.sleep(0.02)  # make the streaming visible in the UI
        yield SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=word + " "))
    yield SimpleNamespace(type="content_block_stop")
    yield SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn"))
    yield SimpleNamespace(type="message_stop")


class _FakeMessages:
    def create(self, **params):
        if params.get("stream"):
            return _stream(_describe_request(params))
        # Non-streaming calls (e.g., translation helpers): return a minimal message
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="[mock]")])


class FakeAnthropic:
    def __init__(self, *args, **kwargs):
        self.messages = _FakeMessages()


if not args.real_claude:
    anthropic.Anthropic = FakeAnthropic

# ---------------------------------------------------------------------------
# App, with outgoing email/mailing-list calls replaced
# ---------------------------------------------------------------------------

from ansari.agents import AnsariClaude  # noqa: E402
from ansari.app import main_api  # noqa: E402
from ansari.ansari_logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _fake_register_to_mailing_list(email: str, first_name: str, last_name: str) -> bool:
    logger.info(f"[mock] Would register {email} to the mailing list")
    return True


class _FakeSendGrid:
    def __init__(self, *args, **kwargs):
        pass

    def send(self, message):
        logger.info(f"[mock] Would send email: {message}")
        return SimpleNamespace(status_code=202)


main_api.register_to_mailing_list = _fake_register_to_mailing_list
main_api.SendGridAPIClient = _FakeSendGrid

# ---------------------------------------------------------------------------
# Search tools (only reachable with --real-claude): answer immediately instead of calling the search APIs
# ---------------------------------------------------------------------------


def _unavailable_tool_call(self, tool_name: str, tool_args: dict, tool_id: str):
    logger.info(f"[mock] Search tool {tool_name} called with {tool_args}; returning 'unavailable'")
    message = (
        "Search is unavailable in this local test environment. Answer from your own knowledge, "
        "and tell the user that the sources could not be searched."
    )
    # Same (message, references, is_error) shape the real method uses for errors
    return (message, None, True)


AnsariClaude.process_tool_call = _unavailable_tool_call


if __name__ == "__main__":
    claude_mode = "REAL Claude (search tools mocked)" if args.real_claude else "mock Claude"
    logger.info(
        f"Mock API on http://{args.host}:{args.port} with {claude_mode}, MongoDB database '{os.environ['MONGO_DB_NAME']}'"
    )
    uvicorn.run(main_api.app, host=args.host, port=args.port)
