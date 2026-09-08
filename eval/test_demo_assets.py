from tools.check_demo_assets import check_demo_assets


def test_public_demo_assets_match_their_reviewed_manifest():
    assert check_demo_assets() == []
