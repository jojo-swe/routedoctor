from routedoctor import diagnose


def test_diagnose_missing_next_hop_and_stale_route() -> None:
    findings = diagnose([{"prefix": "10.0.0.0/24", "age_seconds": 90_000}])
    assert findings == [
        "10.0.0.0/24: missing next hop",
        "10.0.0.0/24: stale route",
    ]
