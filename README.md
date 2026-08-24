# Spotify Lyrics Player

A small Python application that reads the currently playing Spotify track and displays synchronized lyrics character by character.

## Setup

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Add `http://127.0.0.1:8888/callback` as a redirect URI.
3. Install the project:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
```

4. Set the variables from `.env.example` in your shell or deployment environment. Do not commit `.env` or credentials.

## Run

```powershell
.\.venv\Scripts\python -m music_player
```

The first run opens Spotify authorization in a browser. Play a song on an account with Spotify Connect playback access.

## Test

```powershell
.\.venv\Scripts\python -m pytest
```

For a local mock run, set `MUSIC_TEST_MODE=1` before starting the module.

Set `DISPLAY_MODE=overlay` in `.env` to open a translucent, always-on-top,
resizable lyric window. Resize it from any edge or corner. Use the `Display`
menu inside the overlay to switch back to terminal output; close and relaunch
to open the overlay again.

To start the watcher automatically when you sign in to Windows, run
`install_autostart.cmd` once. The watcher stays hidden and launches the lyrics
app only when Spotify is running. The overlay then appears when playback
starts and hides again when playback stops.

If lyrics appear before the vocals, set `LYRICS_DELAY_MS` in `.env` to a larger
value, for example `2000`. Set it to `0` to disable the correction.
