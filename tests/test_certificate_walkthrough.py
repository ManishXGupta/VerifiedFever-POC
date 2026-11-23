import demo_certificate


def test_walkthrough_all_checks_pass():
    assert demo_certificate.main() == 0
    assert all(demo_certificate.results)
