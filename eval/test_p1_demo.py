from tools.audit_p1_demo import audit_p1


def test_p1_demo_audit_passes():
    result = audit_p1()
    assert result.passed, result.findings
    assert result.scenarios == 3
    assert result.replays == 3
    assert result.browser_tests == 3
