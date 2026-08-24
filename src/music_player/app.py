"""Show synchronized lyrics for the Spotify song currently playing."""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
from io import BytesIO
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

import spotipy
from spotipy.oauth2 import SpotifyOAuth
import syncedlyrics
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)


POLL_SECONDS = 0.2
CHARACTER_DELAY_SECONDS = float(os.getenv("CHARACTER_DELAY_SECONDS", "0.04"))
LYRICS_DELAY_MS = int(os.getenv("LYRICS_DELAY_MS", "0"))
LYRICS_PROVIDERS = ["Lrclib", "NetEase", "Megalobiz", "Genius"]
DISPLAY_MODE = os.getenv("DISPLAY_MODE", "terminal").lower()
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

    raw_lyrics = syncedlyrics.search(
        f"{artists} {track['name']}", providers=LYRICS_PROVIDERS
    )
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


def run_terminal(spotify: spotipy.Spotify) -> None:
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


class LyricsOverlay:
    def __init__(self, spotify: spotipy.Spotify) -> None:
        base_prefix = Path(getattr(sys, "base_prefix", sys.prefix))
        tcl_library = base_prefix / "tcl" / "tcl8.6"
        tk_library = base_prefix / "tcl" / "tk8.6"
        if (tcl_library / "init.tcl").exists():
            os.environ["TCL_LIBRARY"] = str(tcl_library)
        if (tk_library / "tk.tcl").exists():
            os.environ["TK_LIBRARY"] = str(tk_library)
        import tkinter as tk
        import tkinter.font as tkfont
        from PIL import Image, ImageTk

        self.spotify = spotify
        self.tk = tk
        self.tkfont = tkfont
        self.Image = Image
        self.ImageTk = ImageTk
        self.root = tk.Tk()
        self.root.title("Spotify Jam Lyrics")
        self.root.geometry("900x300")
        self.root.minsize(620, 260)
        self.root.resizable(True, True)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(
            bg="#121212",
            highlightbackground="#1ed760",
            highlightthickness=1,
        )
        self.root.withdraw()
        self.events: queue.Queue[tuple[str, str, bytes | None]] = queue.Queue()
        self.stop_event = threading.Event()
        self.requested_mode = "overlay"
        self._drag_mode = None
        self._drag_start = None
        self._target_lyric = "Waiting for Spotify..."
        self._rendered_lyric = self._target_lyric
        self._album_photo = None
        self._artwork_data = None
        self._artwork_size = 188
        self._chrome_visible = False
        self._is_fullscreen = False
        self._normal_geometry = self.root.geometry()
        self.chrome_frame = tk.Frame(self.root, bg="#121212", height=28)
        self.chrome_frame.place(x=22, y=8, relwidth=1.0, width=-44, height=28)
        self.chrome_frame.pack_propagate(False)
        self.drag_label = tk.Label(
            self.chrome_frame,
            text="SPOTIFY JAM",
            fg="#b3b3b3",
            bg="#121212",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        )
        self.drag_label.pack(side="left", fill="both", expand=True)
        self.drag_handle = tk.Label(
            self.chrome_frame,
            text="•  •  •  •  •",
            fg="#5f6368",
            bg="#121212",
            font=("Segoe UI", 9),
            cursor="fleur",
        )
        self.drag_handle.place(relx=0.5, rely=0.5, anchor="center")
        self.chrome_controls = tk.Frame(self.chrome_frame, bg="#121212")
        self.chrome_controls.pack(side="right", fill="y")
        self.minimize_button = tk.Button(
            self.chrome_controls,
            text="−",
            command=self._minimize,
            fg="#b3b3b3",
            bg="#121212",
            activeforeground="#ffffff",
            activebackground="#282828",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 13),
            width=2,
            takefocus=False,
        )
        self.minimize_button.pack(side="left", fill="y", pady=(3, 0))
        self.fullscreen_button = tk.Button(
            self.chrome_controls,
            text="□",
            command=self._toggle_fullscreen,
            fg="#b3b3b3",
            bg="#121212",
            activeforeground="#ffffff",
            activebackground="#282828",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 11),
            width=2,
            takefocus=False,
        )
        self.fullscreen_button.pack(side="left", fill="y", pady=(2, 1))
        self.close_button = tk.Button(
            self.chrome_controls,
            text="×",
            command=self._close,
            fg="#b3b3b3",
            bg="#121212",
            activeforeground="#ffffff",
            activebackground="#e81123",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 13),
            width=2,
            takefocus=False,
        )
        self.close_button.pack(side="left", fill="y", pady=(1, 0))
        self.content_frame = tk.Frame(self.root, bg="#121212")
        self.content_frame.pack(fill="both", expand=True, padx=22, pady=(42, 8))
        self.artwork_label = tk.Label(
            self.content_frame,
            text="♫",
            fg="#b3b3b3",
            bg="#282828",
            font=("Segoe UI", 48, "bold"),
            width=6,
            height=3,
        )
        self.artwork_label.pack(side="left", fill="y")
        self.details_frame = tk.Frame(self.content_frame, bg="#121212")
        self.details_frame.pack(side="left", fill="both", expand=True, padx=(22, 0))
        self.session_label = tk.Label(
            self.details_frame,
            text="LISTENING TOGETHER  ·  1 LISTENER",
            fg="#1ed760",
            bg="#121212",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.session_label.pack(fill="x", pady=(4, 10))
        self.lyric_label = tk.Label(
            self.details_frame,
            text="Waiting for Spotify...",
            fg="#f4f1ea",
            bg="#121212",
            font=("Segoe UI", 24, "bold"),
            wraplength=0,
            justify="left",
            anchor="w",
            height=1,
        )
        self.lyric_label.pack(fill="both", expand=True)
        self.track_label = tk.Label(
            self.details_frame,
            text="",
            fg="#b3b3b3",
            bg="#121212",
            font=("Segoe UI", 11),
            anchor="w",
        )
        self.track_label.pack(fill="x", pady=(8, 0))
        self.participant_label = tk.Label(
            self.root,
            text="●  YOU",
            fg="#f4f1ea",
            bg="#121212",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.participant_label.pack(fill="x", padx=22, pady=(0, 14))
        self.root.bind("<Configure>", self._resize_text)
        self.root.bind_all("<Button-3>", self._show_menu)
        self.root.bind_all("<Escape>", lambda _event: self._close())
        self.root.bind_all("<Motion>", self._update_cursor)
        self.root.bind_all("<ButtonPress-1>", self._start_drag)
        self.root.bind_all("<B1-Motion>", self._drag_window)
        self.root.bind_all("<ButtonRelease-1>", self._stop_drag)
        self.root.bind("<Enter>", lambda _event: self._show_chrome())
        self.root.bind("<Leave>", self._hide_chrome_if_outside)
        self.root.bind("<FocusIn>", lambda _event: self._show_chrome())
        self.root.bind("<FocusOut>", lambda _event: self._hide_chrome())
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._build_menu()
        self._hide_chrome()

    def _build_menu(self) -> None:
        display_menu = self.tk.Menu(self.root, tearoff=False)
        display_menu.add_command(label="Terminal", command=self._switch_to_terminal)
        display_menu.add_command(label="Overlay", state="disabled")
        display_menu.add_separator()
        display_menu.add_command(label="Close", command=self._close)
        self.context_menu = display_menu

    def _show_menu(self, event) -> None:
        self.context_menu.post(event.x_root, event.y_root)

    def _edge_at(self, event) -> str:
        border = 8
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        horizontal = "left" if event.x <= border else "right" if event.x >= width - border else ""
        vertical = "top" if event.y <= border else "bottom" if event.y >= height - border else ""
        return vertical + horizontal

    def _update_cursor(self, event) -> None:
        pointer_x, pointer_y = self.root.winfo_pointerxy()
        inside = (
            self.root.winfo_rootx() <= pointer_x < self.root.winfo_rootx() + self.root.winfo_width()
            and self.root.winfo_rooty() <= pointer_y < self.root.winfo_rooty() + self.root.winfo_height()
        )
        if inside:
            self._show_chrome()
        cursors = {
            "topleft": "size_nw_se", "bottomright": "size_nw_se",
            "topright": "size_ne_sw", "bottomleft": "size_ne_sw",
            "top": "size_ns", "bottom": "size_ns",
            "left": "size_we", "right": "size_we",
        }
        self.root.configure(cursor=cursors.get(self._edge_at(event), "arrow"))

    def _start_drag(self, event) -> None:
        if event.widget in (self.fullscreen_button, self.minimize_button, self.close_button):
            return
        self._drag_mode = self._edge_at(event) or "move"
        self._drag_start = (
            event.x_root,
            event.y_root,
            self.root.winfo_x(),
            self.root.winfo_y(),
            self.root.winfo_width(),
            self.root.winfo_height(),
        )

    def _drag_window(self, event) -> None:
        if not self._drag_start:
            return
        start_x, start_y, window_x, window_y, width, height = self._drag_start
        delta_x = event.x_root - start_x
        delta_y = event.y_root - start_y
        if self._drag_mode == "move":
            self.root.geometry(
                f"{width}x{height}+{window_x + delta_x}+{window_y + delta_y}"
            )
            return
        new_x, new_y, new_width, new_height = window_x, window_y, width, height
        if "left" in self._drag_mode:
            new_x = window_x + delta_x
            new_width = width - delta_x
        if "right" in self._drag_mode:
            new_width = width + delta_x
        if "top" in self._drag_mode:
            new_y = window_y + delta_y
            new_height = height - delta_y
        if "bottom" in self._drag_mode:
            new_height = height + delta_y
        if new_width >= 260 and new_height >= 100:
            self.root.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")

    def _stop_drag(self, _event) -> None:
        self._drag_mode = None
        self._drag_start = None

    def _resize_text(self, event) -> None:
        if event.widget is not self.root:
            return
        self._fit_lyric_text()
        self._artwork_size = max(140, min(188, event.height - 92))
        if self._artwork_data:
            self._set_artwork(self._artwork_data)

    def _fit_lyric_text(self) -> None:
        self.root.update_idletasks()
        available_width = max(1, self.details_frame.winfo_width())
        size = min(42, max(14, self.root.winfo_width() // 24))
        font = self.tkfont.Font(family="Segoe UI", size=size, weight="bold")
        while size > 8 and font.measure(self._rendered_lyric) > available_width:
            size -= 1
            font.configure(size=size)
        self.lyric_label.configure(font=font, wraplength=0)

    def _set_artwork(self, artwork: bytes) -> None:
        image = self.Image.open(BytesIO(artwork)).convert("RGB")
        image.thumbnail((self._artwork_size, self._artwork_size))
        self._album_photo = self.ImageTk.PhotoImage(image)
        self.artwork_label.configure(image=self._album_photo, text="")

    def _switch_to_terminal(self) -> None:
        self.requested_mode = "terminal"
        self._close()

    def _show_chrome(self) -> None:
        if not self._chrome_visible:
            self.chrome_frame.place(x=22, y=8, relwidth=1.0, width=-44, height=28)
            self._chrome_visible = True

    def _hide_chrome(self) -> None:
        if self._chrome_visible:
            self.chrome_frame.place_forget()
            self._chrome_visible = False

    def _hide_chrome_if_outside(self, _event) -> None:
        pointer_x, pointer_y = self.root.winfo_pointerxy()
        inside = (
            self.root.winfo_rootx() <= pointer_x < self.root.winfo_rootx() + self.root.winfo_width()
            and self.root.winfo_rooty() <= pointer_y < self.root.winfo_rooty() + self.root.winfo_height()
        )
        if not inside:
            self._hide_chrome()

    def _minimize(self) -> None:
        self.root.overrideredirect(False)
        self.root.iconify()
        self._hide_chrome()

    def _toggle_fullscreen(self) -> None:
        self._is_fullscreen = not self._is_fullscreen
        if self._is_fullscreen:
            self._normal_geometry = self.root.geometry()
            self.root.attributes("-fullscreen", True)
            self.fullscreen_button.configure(text="❐")
        else:
            self.root.attributes("-fullscreen", False)
            self.root.geometry(self._normal_geometry)
            self.fullscreen_button.configure(text="□")

    def _close(self) -> None:
        self.stop_event.set()
        self.root.destroy()

    def _poll_spotify(self) -> None:
        last_track_id = None
        while not self.stop_event.is_set():
            try:
                playback = self.spotify.current_playback()
                if playback and playback.get("is_playing") and playback.get("item"):
                    track = playback["item"]
                    if track["id"] != last_track_id:
                        last_track_id = track["id"]
                        lyrics = fetch_lyrics(track)
                    else:
                        lyrics = LYRICS_CACHE.get(track["id"], [])
                    progress_ms = playback.get("progress_ms", 0)
                    start_times = [line.start_ms for line in lyrics]
                    index = bisect_right(start_times, max(0, progress_ms - LYRICS_DELAY_MS)) - 1
                    line = lyrics[index].text if index >= 0 else "Waiting for lyrics..."
                    artist = track["artists"][0]["name"]
                    artwork = None
                    images = track.get("album", {}).get("images", [])
                    if images:
                        try:
                            with urlopen(images[0]["url"], timeout=4) as response:
                                artwork = response.read()
                        except Exception:
                            pass
                    self.events.put((line, f"{track['name']}  /  {artist}", artwork))
                else:
                    self.events.put(("", "", None))
            except Exception as error:
                self.events.put(("Spotify connection unavailable", str(error), None))
            self.stop_event.wait(POLL_SECONDS)

    def _consume_events(self) -> None:
        try:
            while True:
                line, track, artwork = self.events.get_nowait()
                if not track:
                    self.root.withdraw()
                    continue
                if self.root.state() != "iconic":
                    self.root.deiconify()
                if artwork:
                    self._artwork_data = artwork
                    self._set_artwork(artwork)
                if line != self._target_lyric:
                    self._target_lyric = line
                    self._rendered_lyric = line
                    self.lyric_label.configure(text=line)
                    self._fit_lyric_text()
                self.track_label.configure(text=track)
        except queue.Empty:
            pass
        if not self.stop_event.is_set():
            self.root.after(40, self._consume_events)

    def run(self) -> str:
        threading.Thread(target=self._poll_spotify, daemon=True).start()
        self.root.after(40, self._consume_events)
        self.root.mainloop()
        return self.requested_mode


def run() -> None:
    spotify = make_spotify_client()
    if DISPLAY_MODE == "overlay":
        mode = LyricsOverlay(spotify).run()
        if mode == "terminal":
            run_terminal(spotify)
        return
    run_terminal(spotify)
