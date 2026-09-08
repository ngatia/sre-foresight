"""Inject a burn into the mock and a deploy event into the app, then poll /api/slos."""
import sys
import time
import httpx

APP = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
MOCK = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:9090"

httpx.post(f"{MOCK}/inject/burn", params={"good": 0.80})
from datetime import datetime, timezone  # noqa: E402
httpx.post(f"{APP}/api/events", json={
    "service": "demo", "event_type": "deploy", "source": "argocd",
    "description": "deploy demo v9 (bad release)",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
print("Injected burn + deploy. Watch the dashboard: forecast should bend, correlation should name v9.")
for _ in range(6):
    time.sleep(10)
    print(httpx.get(f"{APP}/api/slos").json())
