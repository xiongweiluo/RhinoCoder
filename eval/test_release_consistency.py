from tools.check_release_consistency import check_release_consistency


def test_repository_release_metadata_and_docs_are_consistent():
    assert check_release_consistency() == []
