from events.argocd import argocd_app_to_change_event


def test_maps_synced_app():
    app = {"metadata": {"name": "resume"},
           "status": {"operationState": {"phase": "Succeeded",
                       "finishedAt": "2026-09-08T12:00:00Z",
                       "operation": {"sync": {"revision": "abc123"}}},
                      "sync": {"status": "Synced"}}}
    e = argocd_app_to_change_event(app)
    assert e is not None and e.service == "resume" and e.event_type == "deploy"
    assert "abc123"[:7] in e.description


def test_ignores_unfinished():
    app = {"metadata": {"name": "resume"},
           "status": {"operationState": {"phase": "Running"}}}
    assert argocd_app_to_change_event(app) is None
