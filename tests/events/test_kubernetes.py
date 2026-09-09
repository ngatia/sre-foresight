from events.kubernetes import deployment_to_change_event


def test_maps_new_generation_to_deploy():
    obj = {"metadata": {"name": "resume", "namespace": "web", "generation": 4,
                        "labels": {"app": "resume"},
                        "annotations": {"deployment.kubernetes.io/revision": "4"}},
           "status": {"observedGeneration": 3}}
    e = deployment_to_change_event(obj)
    assert e is not None
    assert e.service == "resume" and e.event_type == "deploy"
    assert e.source_system == "kubernetes"
    assert "resume" in e.description


def test_no_generation_bump_is_none():
    obj = {"metadata": {"name": "resume", "generation": 3, "labels": {"app": "resume"}},
           "status": {"observedGeneration": 3}}
    assert deployment_to_change_event(obj) is None
