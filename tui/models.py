"""Data models and normalizers for YouTube Music results.

ytmusicapi result shapes have drifted slightly across versions, so every
normalizer here is defensive: it probes several well-known keys and falls
back to empty values instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .format import parse_duration


def _get(mapping: Any, *keys, default=""):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def _first_artist(payload: Dict[str, Any]) -> str:
    artists = payload.get("artists")
    if isinstance(artists, list) and artists:
        first = artists[0]
        if isinstance(first, dict):
            return str(_get(first, "name", default=""))
        if isinstance(first, str):
            return first
    for key in ("artist", "channel", "author", "byline"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict):
            name = _get(value, "name", default="")
            if name:
                return str(name)
    return ""


@dataclass
class Track:
    """A playable YouTube Music song."""

    video_id: str
    title: str
    artist: str = ""
    duration_s: int = 0
    album: str = ""
    available: bool = True
    liked: Optional[bool] = None

    @property
    def watch_url(self) -> str:
        return f"https://music.youtube.com/watch?v={self.video_id}"

    @property
    def duration_text(self) -> str:
        from .format import format_duration

        return format_duration(self.duration_s) if self.duration_s else ""

    def label(self) -> str:
        if self.artist:
            return f"{self.title} — {self.artist}"
        return self.title

    def to_state(self) -> Dict[str, Any]:
        return {
            "videoId": self.video_id,
            "title": self.title,
            "artist": self.artist,
            "duration": self.duration_s,
            "album": self.album,
        }

    @classmethod
    def from_state(cls, payload: Dict[str, Any]) -> "Track":
        return cls(
            video_id=str(_get(payload, "videoId", "video_id", default="")),
            title=str(_get(payload, "title", default="")),
            artist=str(_get(payload, "artist", default="")),
            duration_s=parse_duration(_get(payload, "duration", default=0)),
            album=str(_get(payload, "album", default="")),
        )

    @classmethod
    def from_result(cls, payload: Dict[str, Any]) -> Optional["Track"]:
        video_id = _get(payload, "videoId", "video_id", default="")
        if not video_id:
            return None
        album = payload.get("album")
        album_name = ""
        if isinstance(album, dict):
            album_name = str(_get(album, "name", default=""))
        elif isinstance(album, str):
            album_name = album
        return cls(
            video_id=str(video_id),
            title=str(_get(payload, "title", default="")).strip(),
            artist=_first_artist(payload),
            duration_s=parse_duration(
                _get(payload, "duration", "duration_seconds", "lengthSeconds", default=0)
            ),
            album=album_name,
            available=payload.get("isAvailable", True) is not False,
        )


def tracks_from(results) -> List[Track]:
    tracks: List[Track] = []
    if isinstance(results, dict):
        results = results.get("tracks") or results.get("results") or []
    if not isinstance(results, list):
        return tracks
    for item in results:
        if not isinstance(item, dict):
            continue
        track = Track.from_result(item)
        if track and track.available:
            tracks.append(track)
    return tracks


@dataclass
class Collection:
    """A playlist, album, or other browsable collection."""

    browse_id: str
    title: str
    subtitle: str = ""
    kind: str = "playlist"  # playlist | album | single | ep
    playlist_id: str = ""
    track_count: int = 0

    def to_state(self) -> Dict[str, Any]:
        return {
            "browseId": self.browse_id,
            "playlistId": self.playlist_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "kind": self.kind,
            "count": self.track_count,
        }


def collections_from(results, kind: str = "playlist") -> List[Collection]:
    out: List[Collection] = []
    if isinstance(results, dict):
        results = results.get("results") or results.get("contents") or []
    if not isinstance(results, list):
        return out
    for item in results:
        if not isinstance(item, dict):
            continue
        browse_id = str(_get(item, "browseId", default=""))
        playlist_id = str(_get(item, "playlistId", default=""))
        if not browse_id and not playlist_id:
            continue
        if not browse_id:
            browse_id = playlist_id
        title = str(_get(item, "title", "artist", "name", default="")).strip()
        if not title:
            continue
        subtitle = str(_get(item, "subtitle", "artist", "author", "year", default=""))
        count = 0
        raw_count = _get(item, "count", "trackCount", default="")
        try:
            count = int(str(raw_count).split(" ")[0]) if str(raw_count).strip() else 0
        except ValueError:
            count = 0
        out.append(
            Collection(
                browse_id=browse_id,
                playlist_id=playlist_id,
                title=title,
                subtitle=subtitle,
                kind=kind,
                track_count=count,
            )
        )
    return out


@dataclass
class ArtistRef:
    browse_id: str
    name: str
    subtitle: str = ""


def artists_from(results) -> List[ArtistRef]:
    out: List[ArtistRef] = []
    if isinstance(results, dict):
        results = results.get("results") or results.get("contents") or []
    if not isinstance(results, list):
        return out
    for item in results:
        if not isinstance(item, dict):
            continue
        browse_id = str(_get(item, "browseId", default=""))
        name = str(_get(item, "artist", "name", "title", default="")).strip()
        if not browse_id or not name:
            continue
        out.append(ArtistRef(browse_id=browse_id, name=name,
                             subtitle=str(_get(item, "subtitle", default=""))))
    return out


@dataclass
class Shelf:
    """A row of the personalized homepage."""

    title: str
    tracks: List[Track] = field(default_factory=list)
    collections: List[Collection] = field(default_factory=list)
    videos: List[Track] = field(default_factory=list)


def shelves_from(home_results) -> List[Shelf]:
    shelves: List[Shelf] = []
    if not isinstance(home_results, list):
        return shelves
    for item in home_results:
        if not isinstance(item, dict):
            continue
        title = str(_get(item, "title", default="")).strip()
        contents = item.get("contents") or item.get("content") or []
        if not title or not isinstance(contents, list):
            continue
        shelf = Shelf(title=title)
        for entry in contents:
            if not isinstance(entry, dict):
                continue
            if entry.get("videoId"):
                track = Track.from_result(entry)
                if track:
                    shelf.videos.append(track)
                    continue
            browse_id = str(_get(entry, "browseId", default=""))
            playlist_id = str(_get(entry, "playlistId", default=""))
            coll_title = str(_get(entry, "title", default="")).strip()
            if (browse_id or playlist_id) and coll_title:
                kind = "album" if browse_id.startswith("MPREb") else "playlist"
                shelf.collections.append(
                    Collection(
                        browse_id=browse_id or playlist_id,
                        playlist_id=playlist_id,
                        title=coll_title,
                        subtitle=str(_get(entry, "subtitle", default="")),
                        kind=kind,
                    )
                )
        if shelf.tracks or shelf.collections or shelf.videos:
            shelves.append(shelf)
    return shelves
