from music_player.app import make_spotify_client


def test_local_mode_client_returns_stub(monkeypatch):
    monkeypatch.setenv("MUSIC_TEST_MODE", "1")

    playback = make_spotify_client().current_playback()

    assert playback["is_playing"] is True
    assert playback["item"]["name"]
    assert playback["item"]["artists"][0]["name"]
