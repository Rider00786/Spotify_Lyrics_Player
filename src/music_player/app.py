"""Show synchronized lyrics for the Spotify song currently playing."""

from __future__ import annotations

import os
import re
import sys
import time
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import syncedlyrics
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)


POLL_SECONDS = 0.5
CHARACTER_DELAY_SECONDS = 0.05
LYRICS_DELAY_MS = int(os.getenv("LYRICS_DELAY_MS", "1500"))
TIMESTAMP_PATTERN = re.compile(r"\[(\d+):(\d{2})(?:\.(\d{1,3}))?\](.*)")
LYRICS_CACHE: dict[str, list["LyricLine"]] = {}


@dataclass(frozen=True)
class LyricLine:
    start_ms: int
    text: str


class MockSpotify:
    def current_playback(self):
        return {
            "is_playing": True,
            "progress_ms": 0,
            "item": {
                "id": "test-track-id",
                "name": "Test Song",
                "artists": [{"name": "Test Artist"}],
            },
        }


def make_spotify_client() -> spotipy.Spotify:
    required = ("SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET")
    missing = [name for name in required if not os.getenv(name)]

    if os.getenv("MUSIC_TEST_MODE") == "1" or missing:
        if missing:
            print("Spotify credentials missing. Automatically switching to test mode.")
            os.environ["MUSIC_TEST_MODE"] = "1"
        return MockSpotify()

    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
    scope = "user-read-currently-playing user-read-playback-state"
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=os.environ["SPOTIPY_CLIENT_ID"],
            client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
            scope=scope,
            redirect_uri=redirect_uri,
            open_browser=True,
        )
    )


def parse_lyrics(raw_lyrics: str) -> list[LyricLine]:
    lines: list[LyricLine] = []
    for raw_line in raw_lyrics.splitlines():
        match = TIMESTAMP_PATTERN.match(raw_line)
        if not match:
            continue
        minutes, seconds, fraction, text = match.groups()
        milliseconds = int((fraction or "0").ljust(3, "0"))
        lines.append(LyricLine((int(minutes) * 60 + int(seconds)) * 1000 + milliseconds, text.strip()))
    return sorted(lines, key=lambda line: line.start_ms)


def fetch_lyrics(track: dict) -> list[LyricLine]:
    track_id = track["id"]
    if track_id in LYRICS_CACHE:
        return LYRICS_CACHE[track_id]

    artists = ", ".join(artist["name"] for artist in track["artists"])
    print(f"\nLoading lyrics for {artists} - {track['name']}...\n")
    if os.getenv("MUSIC_TEST_MODE") == "1":
        lyrics = [
            LyricLine(0, "Testing lyrics mode"),
            LyricLine(2000, "This is a mock track"),
            LyricLine(4000, "Spotify is not required"),
        ]
        LYRICS_CACHE[track_id] = lyrics
        return lyrics

    raw_lyrics = syncedlyrics.search(f"{artists} {track['name']}")
    if not raw_lyrics:
        LYRICS_CACHE[track_id] = []
        return []
    lyrics = parse_lyrics(raw_lyrics)
    LYRICS_CACHE[track_id] = lyrics
    return lyrics


def display_line_by_character(text: str) -> None:
    text = text or "..."
    sys.stdout.write("\r")
    for index, character in enumerate(text):
        sys.stdout.write(character)
        sys.stdout.flush()
        if index < len(text) - 1:
            time.sleep(CHARACTER_DELAY_SECONDS)
    sys.stdout.write("\n")
    sys.stdout.flush()


def display_track(spotify: spotipy.Spotify, track: dict, progress_ms: int) -> None:
    print(f"\nNow playing: {track['name']} - {track['artists'][0]['name']}\n")
    lyrics = fetch_lyrics(track)
    if not lyrics:
        print("No synchronized lyrics found for this track.")
        return

    start_times = [line.start_ms for line in lyrics]
    display_progress_ms = max(0, progress_ms - LYRICS_DELAY_MS)
    current_index = bisect_right(start_times, display_progress_ms) - 1
    if current_index >= 0:
        display_line_by_character(lyrics[current_index].text)

    while True:
        playback = spotify.current_playback()
        if not playback or not playback.get("is_playing") or not playback.get("item"):
            return
        current_track = playback["item"]
        if current_track["id"] != track["id"]:
            return

        progress_ms = playback.get("progress_ms", progress_ms)
        display_progress_ms = max(0, progress_ms - LYRICS_DELAY_MS)
        target_index = bisect_right(start_times, display_progress_ms) - 1
        if target_index != current_index:
            current_index = target_index
            if current_index >= 0:
                display_line_by_character(lyrics[current_index].text)
        else:
            time.sleep(POLL_SECONDS)


def run() -> None:
    spotify = make_spotify_client()
    print("Waiting for a song to play on Spotify... Press Ctrl+C to stop.")
    last_track_id = None

    while True:
        playback = spotify.current_playback()
        if playback and playback.get("is_playing") and playback.get("item"):
            track = playback["item"]
            if track["id"] != last_track_id:
                last_track_id = track["id"]
                display_track(spotify, track, playback.get("progress_ms", 0))
                last_track_id = None
        time.sleep(POLL_SECONDS)
