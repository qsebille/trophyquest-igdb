from igdb_enricher.search_candidates.finder.title_cleaner import get_clean_title


def test_clean_game_title_removes_non_alphanumeric_characters():
    title = "lego® batman™: legacy dark knight"

    assert get_clean_title(title) == "lego batman legacy dark knight"


def test_clean_game_title_returns_empty_title_for_only_non_alphanumeric_characters():
    assert get_clean_title("®™:!") == ""
