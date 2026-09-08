import logging

import respx
from httpx import Response
from outputs.notify import Notification, _slack_text, send

N = Notification("Resume - Availability", "resume", "critical", 12.0, 8.0, 4.2,
                 "Deploy resume v2 to prod")

@respx.mock
async def test_posts_to_generic_webhook():
    route = respx.post("http://hook/generic").mock(return_value=Response(200))
    await send(N, webhook_url="http://hook/generic", slack_webhook_url=None)
    assert route.called
    body = route.calls.last.request.content.decode()
    assert "resume" in body and "critical" in body

@respx.mock
async def test_posts_slack_text():
    route = respx.post("http://hook/slack").mock(return_value=Response(200))
    await send(N, webhook_url=None, slack_webhook_url="http://hook/slack")
    assert route.called
    assert '"text"' in route.calls.last.request.content.decode()

@respx.mock
async def test_failure_does_not_raise():
    respx.post("http://hook/x").mock(return_value=Response(500))
    await send(N, webhook_url="http://hook/x", slack_webhook_url=None)  # no exception


def test_slack_text_escapes_mrkdwn_and_strips_newlines():
    n = Notification("Resume - Availability", "resume", "critical", 12.0, 8.0, 4.2,
                     "<script>&\nfoo")
    text = _slack_text(n)
    assert "<script>" not in text
    assert "\n\nfoo" not in text  # no injected line from the raw newline
    assert "&lt;script&gt;&amp;foo" in text
    assert "\r" not in text


@respx.mock
async def test_failed_webhook_does_not_log_secret_path(caplog):
    secret_url = "http://hook/T00/B00/super-secret-token"
    respx.post(secret_url).mock(return_value=Response(500))
    with caplog.at_level(logging.WARNING):
        await send(N, webhook_url=secret_url, slack_webhook_url=None)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "super-secret-token" not in logged
    assert "T00/B00" not in logged
    assert "http://hook" in logged
