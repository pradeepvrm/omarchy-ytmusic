"""Wrapper around ytmusicapi: authentication plus normalized queries.

All calls here are blocking (ytmusicapi uses requests) and must be invoked
from textual thread workers.

Authentication follows ytmusicapi's OAuth setup for custom clients: you
create a Google Cloud OAuth client (TV type) once, then sign in through
Google's device flow. The token lives at ``oauth.json`` and the OAuth client
credentials at ``client.json``, both under the user state directory with
owner-only permissions.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import (
    ArtistRef,
    Collection,
    Shelf,
    Track,
    artists_from,
    collections_from,
    shelves_from,
    tracks_from,
)


def state_home() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(base) / "omarchy-ytmusic"


def oauth_path() -> Path:
    return state_home() / "oauth.json"


def client_credentials_path() -> Path:
    return state_home() / "client.json"


def browser_path() -> Path:
    return state_home() / "browser.json"


def browser_signed_in() -> bool:
    try:
        payload = json.loads(browser_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and bool(payload.get("cookie"))


def oauth_signed_in() -> bool:
    try:
        return (oauth_path().is_file() and oauth_path().stat().st_size > 0
                and client_credentials_path().is_file())
    except OSError:
        return False


def signed_in() -> bool:
    return browser_signed_in() or oauth_signed_in()


def auth_method() -> str:
    """Which credential set will be used: 'browser', 'oauth', or ''."""
    if browser_signed_in():
        return "browser"
    if oauth_signed_in():
        return "oauth"
    return ""


def is_podcast_id(playlist_id: str) -> bool:
    """Whether a playlist id addresses a podcast show.

    Shows use MPSP… ids and surface as VLMPSP… playlist links; both crash
    ytmusicapi's music-playlist parser and need get_podcast instead.
    """
    text = str(playlist_id or "")
    if text.startswith("VL"):
        text = text[2:]
    return text.startswith("MPSP")


def normalize_podcast_id(playlist_id: str) -> str:
    """Strip a VL playlist wrapper so get_podcast receives an MPSP… id."""
    text = str(playlist_id or "")
    if text.startswith("VL"):
        rest = text[2:]
        if rest.startswith("MPSP"):
            return rest
    return text


def store_browser_headers(headers_raw: str) -> None:
    """Parse pasted browser request headers and store browser.json.

    Raises whatever ytmusicapi raises (e.g. YTMusicUserError when the
    required cookie entries are missing).
    """
    from ytmusicapi.auth.browser import setup_browser

    state_home().mkdir(parents=True, exist_ok=True)
    setup_browser(str(browser_path()), headers_raw)
    try:
        browser_path().chmod(0o600)
    except OSError:
        pass


def load_client_credentials() -> Optional[Dict[str, str]]:
    try:
        payload = json.loads(client_credentials_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    client_id = str(payload.get("client_id", "")).strip()
    client_secret = str(payload.get("client_secret", "")).strip()
    if not client_id or not client_secret:
        return None
    return {"client_id": client_id, "client_secret": client_secret}


def store_client_credentials(client_id: str, client_secret: str) -> None:
    state_home().mkdir(parents=True, exist_ok=True)
    client_credentials_path().write_text(
        json.dumps({"client_id": client_id, "client_secret": client_secret}),
        encoding="utf-8",
    )
    try:
        client_credentials_path().chmod(0o600)
    except OSError:
        pass


class DeviceAuthFlow:
    """Google OAuth device flow driven from the TUI.

    ytmusicapi's own ``prompt_for_token`` blocks on ``input()``, which cannot
    work under Textual, so this replays the same library calls with a polling
    loop and progress callbacks. Run :meth:`run` from a thread worker.

    Progress is reported as dicts:
      ``{"phase": "code", "url": ..., "user_code": ..., "interval": ...}``
      ``{"phase": "waiting"}`` while polling
      ``{"phase": "done", "ok": bool, "message": str}`` exactly once.
    """

    def __init__(self, client_id: str, client_secret: str,
                 on_progress: Callable[[Dict[str, Any]], None]) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.on_progress = on_progress
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def _report(self, **payload: Any) -> None:
        try:
            self.on_progress(payload)
        except Exception:
            pass

    def run(self) -> bool:
        from ytmusicapi.auth.oauth import OAuthCredentials, RefreshingToken

        try:
            credentials = OAuthCredentials(self.client_id, self.client_secret)
            code = credentials.get_code()
        except Exception as error:
            self._report(phase="done", ok=False,
                         message=f"could not start the sign-in flow: {error}")
            return False

        verification_url = str(code.get("verification_url", ""))
        user_code = str(code.get("user_code", ""))
        interval = max(1, int(code.get("interval", 5) or 5))
        expires_in = max(60, int(code.get("expires_in", 1800) or 1800))
        self._report(phase="code", url=verification_url, user_code=user_code,
                     interval=interval)

        device_code = str(code.get("device_code", ""))
        deadline = time.monotonic() + expires_in
        raw_token: Optional[Dict[str, Any]] = None
        while time.monotonic() < deadline:
            if self._cancelled.is_set():
                self._report(phase="done", ok=False, message="cancelled")
                return False
            time.sleep(interval)
            if self._cancelled.is_set():
                self._report(phase="done", ok=False, message="cancelled")
                return False
            self._report(phase="waiting")
            try:
                response = credentials.token_from_code(device_code)
            except Exception as error:
                self._report(phase="done", ok=False,
                             message=f"authorization failed: {error}")
                return False
            if "access_token" in response:
                raw_token = response
                break
            error = str(response.get("error", ""))
            if error == "slow_down":
                interval += 5
            elif error not in ("authorization_pending", ""):
                self._report(phase="done", ok=False,
                             message=f"authorization failed: {error}")
                return False

        if raw_token is None:
            self._report(phase="done", ok=False,
                         message="the sign-in code expired; try again")
            return False

        try:
            refresh_expires = raw_token.get("refresh_token_expires_in",
                                            raw_token.get("expires_in", 3600))
            token = RefreshingToken(
                credentials=credentials,
                access_token=str(raw_token["access_token"]),
                refresh_token=str(raw_token["refresh_token"]),
                scope=str(raw_token.get("scope",
                                         "https://www.googleapis.com/auth/youtube")),
                token_type=str(raw_token.get("token_type", "Bearer")),
                expires_in=int(refresh_expires or 3600),
            )
            token.update(raw_token)
            state_home().mkdir(parents=True, exist_ok=True)
            token.local_cache = oauth_path()
            try:
                oauth_path().chmod(0o600)
            except OSError:
                pass
            store_client_credentials(self.client_id, self.client_secret)
        except Exception as error:
            self._report(phase="done", ok=False,
                         message=f"could not save the sign-in token: {error}")
            return False

        self._report(phase="done", ok=True, message="Signed in")
        return True


class YtMusic:
    """Thin, blocking wrapper with cached results."""

    def __init__(self) -> None:
        self._client: Any = None
        self.home_shelves: List[Shelf] = []
        self._account_name: str = ""

    @property
    def authenticated(self) -> bool:
        return signed_in()

    def _yt(self) -> Any:
        if self._client is None:
            if browser_signed_in():
                # Browser-cookie auth is the working method: plain cookie
                # headers exported from music.youtube.com. Preferred over
                # OAuth because YouTube's servers currently reject OAuth
                # Bearer tokens from custom clients with HTTP 400.
                from ytmusicapi import YTMusic as _YTMusic

                try:
                    browser_path().chmod(0o600)
                except OSError:
                    pass
                self._client = _YTMusic(str(browser_path()))
            elif oauth_signed_in():
                from ytmusicapi import YTMusic as _YTMusic
                from ytmusicapi.auth.oauth import OAuthCredentials

                client = load_client_credentials()
                if client is None:
                    raise NotSignedIn()
                credentials = OAuthCredentials(
                    client_id=client["client_id"],
                    client_secret=client["client_secret"],
                )
                try:
                    oauth_path().chmod(0o600)
                except OSError:
                    pass
                self._client = _YTMusic(str(oauth_path()), oauth_credentials=credentials)
            else:
                raise NotSignedIn()
        return self._client

    def reload_auth(self) -> None:
        """Drop the cached client so new credential files take effect."""
        self._client = None
        self.home_shelves = []
        self._account_name = ""

    def sign_out(self) -> None:
        self._client = None
        self.home_shelves = []
        self._account_name = ""
        for path in (browser_path(), oauth_path(), client_credentials_path()):
            try:
                path.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------ queries

    def home(self) -> List[Shelf]:
        # NOTE: the ytmusicapi method is get_home(); there is no .home().
        shelves = shelves_from(self._yt().get_home(limit=6))
        if shelves:
            self.home_shelves = shelves
        return self.home_shelves

    def search(self, query: str, filter_name: Optional[str] = None) -> List[Dict[str, Any]]:
        results = self._yt().search(query, filter=filter_name) if filter_name else \
            self._yt().search(query)
        return results if isinstance(results, list) else []

    def watch_playlist(self, video_id: str, limit: int = 50) -> List[Track]:
        payload = self._yt().get_watch_playlist(video_id, limit=limit)
        tracks = tracks_from(payload.get("tracks") if isinstance(payload, dict) else payload)
        source_track = self.song(video_id)
        if source_track:
            tracks.insert(0, source_track)
        seen = set()
        unique: List[Track] = []
        for track in tracks:
            if track.video_id in seen:
                continue
            seen.add(track.video_id)
            unique.append(track)
        return unique

    def song(self, video_id: str) -> Optional[Track]:
        try:
            payload = self._yt().get_song(video_id)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        details = payload.get("videoDetails") or payload
        if not isinstance(details, dict) or not details.get("videoId"):
            return None
        return Track.from_result(details)

    def playlist(self, playlist_id: str, limit: int = 500) -> Dict[str, Any]:
        if is_podcast_id(playlist_id):
            return self.podcast(playlist_id, limit=limit)
        payload = self._yt().get_playlist(playlist_id, limit=limit)
        if not isinstance(payload, dict):
            return {"title": "Playlist", "tracks": []}
        payload["tracks"] = tracks_from(payload.get("tracks"))
        return payload

    def podcast(self, playlist_id: str, limit: int = 100) -> Dict[str, Any]:
        """Load a podcast show (MPSP… or VLMPSP… id) as episodes.

        Music-playlist parsing crashes on show layouts, so shows need
        ytmusicapi's get_podcast. Episodes carry no artist, so the show
        title fills in as the artist for display and the bar widget.
        """
        payload = self._yt().get_podcast(normalize_podcast_id(playlist_id),
                                         limit=limit)
        if not isinstance(payload, dict):
            return {"title": "Podcast", "tracks": []}
        title = str(payload.get("title") or "Podcast")
        tracks = tracks_from(payload.get("episodes"))
        for track in tracks:
            if not track.artist:
                track.artist = title
        payload["tracks"] = tracks
        payload["title"] = title
        return payload

    def album(self, browse_id: str) -> Dict[str, Any]:
        payload = self._yt().get_album(browse_id)
        if not isinstance(payload, dict):
            return {"title": "Album", "tracks": []}
        payload["tracks"] = tracks_from(payload.get("tracks"))
        return payload

    def artist(self, browse_id: str) -> Dict[str, Any]:
        payload = self._yt().get_artist(browse_id)
        if not isinstance(payload, dict):
            return {"name": "Artist", "tracks": []}
        top = payload.get("tracks") or {}
        payload["track_list"] = tracks_from(top.get("results") if isinstance(top, dict) else [])
        payload["album_list"] = collections_from(
            (payload.get("albums") or {}).get("results")
            if isinstance(payload.get("albums"), dict) else [],
            kind="album",
        )
        payload["single_list"] = collections_from(
            (payload.get("singles") or {}).get("results")
            if isinstance(payload.get("singles"), dict) else [],
            kind="single",
        )
        return payload

    def library_playlists(self, limit: int = 100) -> List[Collection]:
        return collections_from(self._yt().get_library_playlists(limit=limit))

    def library_songs(self, limit: int = 200) -> List[Track]:
        return tracks_from(self._yt().get_library_songs(limit=limit))

    def liked_songs(self, limit: int = 500) -> List[Track]:
        payload = self._yt().get_liked_songs(limit=limit)
        tracks = tracks_from(payload.get("tracks") if isinstance(payload, dict) else payload)
        for track in tracks:
            track.liked = True
        return tracks

    def library_albums(self, limit: int = 100) -> List[Collection]:
        return collections_from(self._yt().get_library_albums(limit=limit), kind="album")

    def library_artists(self, limit: int = 100) -> List[ArtistRef]:
        return artists_from(self._yt().get_library_artists(limit=limit))

    def history(self) -> List[Track]:
        payload = self._yt().get_history()
        tracks: List[Track] = []
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict):
                    inner = entry.get("playlist") or entry
                    tracks.extend(tracks_from(inner.get("tracks") if isinstance(inner, dict) else []))
        seen = set()
        unique: List[Track] = []
        for track in tracks:
            if track.video_id in seen:
                continue
            seen.add(track.video_id)
            unique.append(track)
        return unique[:300]

    def like(self, video_id: str) -> bool:
        return self._rate(video_id, "LIKE")

    def unlike(self, video_id: str) -> bool:
        return self._rate(video_id, "INDIFFERENT")

    def _rate(self, video_id: str, rating: str) -> bool:
        try:
            self._yt().rate_song(video_id, rating)
            return True
        except Exception:
            return False

    def playlists_for_add(self) -> List[Dict[str, Any]]:
        payload = self._yt().get_library_playlists(limit=100)
        return payload if isinstance(payload, list) else []

    def add_to_playlist(self, playlist_id: str, video_id: str) -> str:
        response = self._yt().add_playlist_items(playlist_id, [video_id])
        status = ""
        if isinstance(response, dict):
            status = str(response.get("status", ""))
            if response.get("actions"):
                actions = response.get("actions") or []
                if actions and isinstance(actions[0], dict):
                    status = str(actions[0].get("status", status))
        return status or "STATUS_SUCCEEDED"

    def create_playlist(self, title: str, description: str = "") -> Optional[str]:
        try:
            playlist_id = self._yt().create_playlist(
                title, description=description, privacy_status="PRIVATE"
            )
            return str(playlist_id) if playlist_id else None
        except Exception:
            return None


class NotSignedIn(Exception):
    pass
