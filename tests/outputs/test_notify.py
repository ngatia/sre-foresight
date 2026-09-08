import respx
from httpx import Response
from outputs.notify import Notification, send

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
