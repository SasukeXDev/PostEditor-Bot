from app.links import replace_bot_username


def test_preserves_start_token_exactly():
    source = "https://t.me/OldFileStoreBot?start=AbC_123-%3D&x=1"
    assert replace_bot_username(source, "OldFileStoreBot", "NewFileStoreBot") == \
        "https://t.me/NewFileStoreBot?start=AbC_123-%3D&x=1"


def test_does_not_match_other_bot():
    assert replace_bot_username("https://t.me/SomeOtherBot?start=abc", "OldFileStoreBot", "NewFileStoreBot") is None


def test_preserves_path_and_fragment():
    source = "https://t.me/OldFileStoreBot?start=abc#section"
    assert replace_bot_username(source, "OldFileStoreBot", "NewFileStoreBot") == \
        "https://t.me/NewFileStoreBot?start=abc#section"
