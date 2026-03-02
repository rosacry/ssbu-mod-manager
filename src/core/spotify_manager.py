"""Spotify authentication and playlist export helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from src.core.music_manager import beautify_track_name
from src.models.music import MusicTrack
from src.utils.logger import logger


SPOTIFY_ACCOUNTS_BASE_URL = "https://accounts.spotify.com"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"
SPOTIFY_CALLBACK_HOST = "127.0.0.1"
SPOTIFY_CALLBACK_PATH = "/callback"
SPOTIFY_REDIRECT_URI_DOC = "http://127.0.0.1/callback"
SPOTIFY_TOKEN_EXPIRY_SKEW_SECONDS = 60
SPOTIFY_MATCH_THRESHOLD = 0.78
SPOTIFY_AMBIGUOUS_MARGIN = 0.03
SPOTIFY_SEARCH_LIMIT = 10
SPOTIFY_PLAYLIST_WRITE_CHUNK = 100
SPOTIFY_TIMEOUT_SECONDS = 30
SPOTIFY_AUTH_TIMEOUT_SECONDS = 180
SPOTIFY_HIGH_CONFIDENCE_THRESHOLD = 0.92
SPOTIFY_AMBIGUOUS_CEILING = 0.90
SPOTIFY_SIMILARITY_WEIGHT = 0.7
SPOTIFY_OVERLAP_WEIGHT = 0.3
SPOTIFY_EXACT_MATCH_BONUS = 0.12
SPOTIFY_SERIES_HINT_BONUS = 0.06
SPOTIFY_QUERY_MATCH_BONUS = 0.04
SPOTIFY_DEFAULT_TOKEN_LIFETIME = 3600
SPOTIFY_MIN_TOKEN_LIFETIME = 60
SPOTIFY_SCOPES = (
    "playlist-read-private",
    "playlist-modify-private",
    "playlist-modify-public",
    "user-read-private",
)


class SpotifyError(RuntimeError):
    """Base Spotify integration error."""


class SpotifyAuthError(SpotifyError):
    """Raised for Spotify authentication failures."""


class SpotifyApiError(SpotifyError):
    """Raised for Spotify Web API request failures."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SpotifyProfile:
    user_id: str
    display_name: str


@dataclass(frozen=True)
class SpotifyPlaylist:
    playlist_id: str
    name: str
    owner_id: str
    track_count: int = 0
    public: bool = False
    external_url: str = ""

    @property
    def label(self) -> str:
        suffix = f" ({self.track_count})" if self.track_count >= 0 else ""
        return f"{self.name}{suffix}"


@dataclass(frozen=True)
class SpotifyTrackMatch:
    uri: str
    name: str
    artist_names: tuple[str, ...]
    album_name: str
    score: float
    query_used: str


@dataclass
class SpotifyExportReport:
    playlist_id: str
    playlist_name: str
    playlist_url: str = ""
    attempted: int = 0
    matched: int = 0
    added: int = 0
    duplicate_skips: int = 0
    unresolved: list[str] = field(default_factory=list)
    low_confidence: list[str] = field(default_factory=list)
    added_tracks: list[str] = field(default_factory=list)


class _SpotifyCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != SPOTIFY_CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        self.server.spotify_code = params.get("code", [None])[0]  # type: ignore[attr-defined]
        self.server.spotify_error = params.get("error", [None])[0]  # type: ignore[attr-defined]
        self.server.spotify_state = params.get("state", [None])[0]  # type: ignore[attr-defined]
        self.server.spotify_event.set()  # type: ignore[attr-defined]

        is_error = bool(self.server.spotify_error)  # type: ignore[attr-defined]
        body = (
            "<html><body style='font-family:Segoe UI, sans-serif; background:#111827; "
            "color:#f3f4f6; padding:24px;'>"
            "<h2>Spotify authorization received</h2>"
            "<p>You can close this window and return to SSBU Mod Manager.</p>"
            "</body></html>"
        )
        if is_error:
            body = (
                "<html><body style='font-family:Segoe UI, sans-serif; background:#111827; "
                "color:#fca5a5; padding:24px;'>"
                "<h2>Spotify authorization failed</h2>"
                "<p>You can close this window and return to SSBU Mod Manager.</p>"
                "</body></html>"
            )

        encoded = body.encode("utf-8")
        self.send_response(200 if not is_error else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class SpotifyManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    @property
    def settings(self):
        return self.config_manager.settings

    def is_authenticated(self) -> bool:
        settings = self.settings
        return bool(
            settings.spotify_client_id.strip()
            and settings.spotify_refresh_token.strip()
        )

    def disconnect(self) -> None:
        settings = self.settings
        settings.spotify_access_token = ""
        settings.spotify_refresh_token = ""
        settings.spotify_token_expires_at = 0
        settings.spotify_user_id = ""
        settings.spotify_display_name = ""
        settings.spotify_last_playlist_id = ""
        self.config_manager.save(settings)

    def connect(self, client_id: str, timeout_seconds: int = SPOTIFY_AUTH_TIMEOUT_SECONDS) -> SpotifyProfile:
        cleaned_client_id = (client_id or "").strip()
        if not cleaned_client_id:
            raise SpotifyAuthError("Enter a Spotify client ID first.")

        code_verifier = secrets.token_urlsafe(64)
        challenge = self._build_code_challenge(code_verifier)
        state = secrets.token_urlsafe(24)

        server = self._start_callback_server()
        redirect_uri = (
            f"http://{SPOTIFY_CALLBACK_HOST}:{server.server_port}{SPOTIFY_CALLBACK_PATH}"
        )
        auth_url = self._build_authorize_url(cleaned_client_id, challenge, state, redirect_uri)

        if not webbrowser.open(auth_url):
            server.shutdown()
            server.server_close()
            raise SpotifyAuthError(
                "Could not open a browser for Spotify sign-in. "
                "Check your default browser configuration and try again."
            )

        logger.info("Spotify", "Waiting for Spotify authorization callback")
        if not server.spotify_event.wait(timeout_seconds):  # type: ignore[attr-defined]
            server.shutdown()
            server.server_close()
            raise SpotifyAuthError("Timed out waiting for Spotify authorization.")

        server.shutdown()
        server.server_close()

        callback_error = getattr(server, "spotify_error", None)
        callback_state = getattr(server, "spotify_state", None)
        callback_code = getattr(server, "spotify_code", None)

        if callback_error:
            raise SpotifyAuthError(f"Spotify authorization failed: {callback_error}")
        if callback_state != state:
            raise SpotifyAuthError("Spotify authorization response could not be verified.")
        if not callback_code:
            raise SpotifyAuthError("Spotify did not return an authorization code.")

        tokens = self._exchange_code_for_tokens(
            cleaned_client_id,
            callback_code,
            redirect_uri,
            code_verifier,
        )
        self._store_token_bundle(cleaned_client_id, tokens)
        profile = self.get_current_profile(force_refresh=True)
        logger.info("Spotify", f"Connected Spotify account: {profile.display_name or profile.user_id}")
        return profile

    def get_current_profile(self, force_refresh: bool = False) -> SpotifyProfile:
        settings = self.settings
        if not force_refresh and settings.spotify_user_id.strip():
            return SpotifyProfile(
                user_id=settings.spotify_user_id,
                display_name=settings.spotify_display_name or settings.spotify_user_id,
            )

        payload = self._api_request("GET", "/me")
        user_id = str(payload.get("id", "") or "").strip()
        if not user_id:
            raise SpotifyApiError("Spotify did not return the current user ID.")
        display_name = str(payload.get("display_name", "") or user_id)
        settings.spotify_user_id = user_id
        settings.spotify_display_name = display_name
        self.config_manager.save(settings)
        return SpotifyProfile(user_id=user_id, display_name=display_name)

    def list_owned_playlists(self) -> list[SpotifyPlaylist]:
        profile = self.get_current_profile()
        playlists: list[SpotifyPlaylist] = []
        offset = 0

        while True:
            payload = self._api_request(
                "GET",
                "/me/playlists",
                query={"limit": 50, "offset": offset},
            )
            items = payload.get("items") or []
            if not isinstance(items, list):
                items = []

            for raw in items:
                owner = raw.get("owner") or {}
                owner_id = str(owner.get("id", "") or "")
                if owner_id != profile.user_id:
                    continue
                tracks = raw.get("tracks") or {}
                external_urls = raw.get("external_urls") or {}
                playlists.append(
                    SpotifyPlaylist(
                        playlist_id=str(raw.get("id", "") or ""),
                        name=str(raw.get("name", "") or "Untitled Playlist"),
                        owner_id=owner_id,
                        track_count=int(tracks.get("total", 0) or 0),
                        public=bool(raw.get("public", False)),
                        external_url=str(external_urls.get("spotify", "") or ""),
                    )
                )

            next_url = payload.get("next")
            if not next_url:
                break
            offset += len(items)
            if not items:
                break

        playlists = [playlist for playlist in playlists if playlist.playlist_id]
        playlists.sort(key=lambda playlist: playlist.name.lower())
        return playlists

    def create_playlist(
        self,
        name: str,
        *,
        public: bool = False,
        description: str = "",
    ) -> SpotifyPlaylist:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise SpotifyApiError("Enter a playlist name first.")

        payload = self._api_request(
            "POST",
            "/me/playlists",
            json_body={
                "name": cleaned_name,
                "public": bool(public),
                "description": description.strip(),
            },
        )
        owner = payload.get("owner") or {}
        tracks = payload.get("tracks") or {}
        external_urls = payload.get("external_urls") or {}
        playlist = SpotifyPlaylist(
            playlist_id=str(payload.get("id", "") or ""),
            name=str(payload.get("name", "") or cleaned_name),
            owner_id=str(owner.get("id", "") or self.get_current_profile().user_id),
            track_count=int(tracks.get("total", 0) or 0),
            public=bool(payload.get("public", False)),
            external_url=str(external_urls.get("spotify", "") or ""),
        )
        if not playlist.playlist_id:
            raise SpotifyApiError("Spotify did not return a playlist ID.")
        return playlist

    def export_tracks_to_playlist(
        self,
        playlist: SpotifyPlaylist,
        tracks: list[MusicTrack],
    ) -> SpotifyExportReport:
        if not tracks:
            raise SpotifyApiError("No tracks were selected for Spotify export.")

        existing_uris = self.get_playlist_track_uris(playlist.playlist_id)
        pending_uris: list[str] = []
        pending_uri_set = set()
        report = SpotifyExportReport(
            playlist_id=playlist.playlist_id,
            playlist_name=playlist.name,
            playlist_url=playlist.external_url,
            attempted=len(tracks),
        )

        for track in tracks:
            match, reason = self.find_best_match_for_track(track)
            if match is None:
                if reason == "low_confidence":
                    report.low_confidence.append(self._display_track_name(track))
                else:
                    report.unresolved.append(self._display_track_name(track))
                continue

            report.matched += 1
            if match.uri in existing_uris or match.uri in pending_uri_set:
                report.duplicate_skips += 1
                continue

            pending_uri_set.add(match.uri)
            pending_uris.append(match.uri)
            report.added_tracks.append(self._display_track_name(track))

        if pending_uris:
            self._add_tracks_to_playlist(playlist.playlist_id, pending_uris)
            report.added = len(pending_uris)

        return report

    def find_best_match_for_track(
        self,
        track: MusicTrack,
    ) -> tuple[Optional[SpotifyTrackMatch], str]:
        queries = self._build_search_queries(track)
        best_match: Optional[SpotifyTrackMatch] = None
        second_best_score = 0.0

        for query in queries:
            payload = self._api_request(
                "GET",
                "/search",
                query={"q": query, "type": "track", "limit": SPOTIFY_SEARCH_LIMIT},
            )
            items = ((payload.get("tracks") or {}).get("items")) or []
            if not isinstance(items, list):
                items = []

            scored_matches = [
                self._score_search_result(track, query, item)
                for item in items
            ]
            scored_matches = [match for match in scored_matches if match is not None]
            scored_matches.sort(key=lambda match: match.score, reverse=True)

            if scored_matches:
                if best_match is None or scored_matches[0].score > best_match.score:
                    if best_match is not None:
                        second_best_score = max(second_best_score, best_match.score)
                    best_match = scored_matches[0]
                if len(scored_matches) > 1:
                    second_best_score = max(second_best_score, scored_matches[1].score)

            if best_match and best_match.score >= SPOTIFY_HIGH_CONFIDENCE_THRESHOLD:
                break

        if best_match is None:
            return None, "unresolved"
        if best_match.score < SPOTIFY_MATCH_THRESHOLD:
            return None, "low_confidence"
        if (
            second_best_score
            and (best_match.score - second_best_score) < SPOTIFY_AMBIGUOUS_MARGIN
            and best_match.score < SPOTIFY_AMBIGUOUS_CEILING
        ):
            return None, "low_confidence"
        return best_match, "matched"

    def get_playlist_track_uris(self, playlist_id: str) -> set[str]:
        uris: set[str] = set()
        next_url = f"/playlists/{playlist_id}/items"
        query = {"limit": 100}

        while next_url:
            payload = self._api_request("GET", next_url, query=query)
            items = payload.get("items") or []
            if not isinstance(items, list):
                items = []

            for item in items:
                candidate = item.get("track") or item.get("item") or item
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("is_local") or item.get("is_local"):
                    continue
                uri = str(candidate.get("uri", "") or "")
                if uri.startswith("spotify:track:"):
                    uris.add(uri)

            next_url = payload.get("next") or ""
            if next_url.startswith(SPOTIFY_API_BASE_URL):
                next_url = next_url[len(SPOTIFY_API_BASE_URL):]
            query = None

        return uris

    def _add_tracks_to_playlist(self, playlist_id: str, uris: list[str]) -> None:
        for index in range(0, len(uris), SPOTIFY_PLAYLIST_WRITE_CHUNK):
            chunk = uris[index:index + SPOTIFY_PLAYLIST_WRITE_CHUNK]
            self._api_request(
                "POST",
                f"/playlists/{playlist_id}/items",
                json_body={"uris": chunk},
            )

    def _api_request(
        self,
        method: str,
        path_or_url: str,
        *,
        query: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        url = path_or_url
        if not url.startswith("http"):
            url = f"{SPOTIFY_API_BASE_URL}{path_or_url}"
        if query:
            query_string = urllib.parse.urlencode(query, doseq=True)
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query_string}"

        token = self.ensure_access_token()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        body = None
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=SPOTIFY_TIMEOUT_SECONDS) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry_on_401:
                self.refresh_access_token(force=True)
                return self._api_request(
                    method,
                    path_or_url,
                    query=query,
                    json_body=json_body,
                    retry_on_401=False,
                )
            raise self._build_api_error(e) from e
        except urllib.error.URLError as e:
            raise SpotifyApiError(f"Spotify request failed: {e.reason}") from e

    def ensure_access_token(self) -> str:
        settings = self.settings
        if not settings.spotify_client_id.strip() or not settings.spotify_refresh_token.strip():
            raise SpotifyAuthError("Connect a Spotify account first.")
        expires_at = int(settings.spotify_token_expires_at or 0)
        if settings.spotify_access_token.strip() and time.time() < max(0, expires_at - SPOTIFY_TOKEN_EXPIRY_SKEW_SECONDS):
            return settings.spotify_access_token
        return self.refresh_access_token(force=False)

    def refresh_access_token(self, force: bool = False) -> str:
        settings = self.settings
        if not settings.spotify_client_id.strip() or not settings.spotify_refresh_token.strip():
            raise SpotifyAuthError("Connect a Spotify account first.")
        expires_at = int(settings.spotify_token_expires_at or 0)
        if (
            not force
            and settings.spotify_access_token.strip()
            and time.time() < max(0, expires_at - SPOTIFY_TOKEN_EXPIRY_SKEW_SECONDS)
        ):
            return settings.spotify_access_token

        payload = self._post_form(
            f"{SPOTIFY_ACCOUNTS_BASE_URL}/api/token",
            {
                "grant_type": "refresh_token",
                "refresh_token": settings.spotify_refresh_token,
                "client_id": settings.spotify_client_id,
            },
        )
        self._store_token_bundle(settings.spotify_client_id, payload)
        return self.settings.spotify_access_token

    def _exchange_code_for_tokens(
        self,
        client_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        return self._post_form(
            f"{SPOTIFY_ACCOUNTS_BASE_URL}/api/token",
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )

    def _post_form(self, url: str, data: dict[str, Any]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=SPOTIFY_TIMEOUT_SECONDS) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise self._build_api_error(e) from e
        except urllib.error.URLError as e:
            raise SpotifyApiError(f"Spotify authentication request failed: {e.reason}") from e

    def _store_token_bundle(self, client_id: str, payload: dict[str, Any]) -> None:
        access_token = str(payload.get("access_token", "") or "").strip()
        if not access_token:
            raise SpotifyAuthError("Spotify did not return an access token.")

        settings = self.settings
        settings.spotify_client_id = client_id.strip()
        settings.spotify_access_token = access_token
        refresh_token = str(payload.get("refresh_token", "") or "").strip()
        if refresh_token:
            settings.spotify_refresh_token = refresh_token

        expires_in = int(payload.get("expires_in", SPOTIFY_DEFAULT_TOKEN_LIFETIME) or SPOTIFY_DEFAULT_TOKEN_LIFETIME)
        settings.spotify_token_expires_at = int(time.time()) + max(SPOTIFY_MIN_TOKEN_LIFETIME, expires_in)
        self.config_manager.save(settings)

    @staticmethod
    def _build_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def _build_authorize_url(
        self,
        client_id: str,
        code_challenge: str,
        state: str,
        redirect_uri: str,
    ) -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "scope": " ".join(SPOTIFY_SCOPES),
                "state": state,
                "code_challenge_method": "S256",
                "code_challenge": code_challenge,
            }
        )
        return f"{SPOTIFY_ACCOUNTS_BASE_URL}/authorize?{query}"

    def _start_callback_server(self) -> ThreadingHTTPServer:
        server = ThreadingHTTPServer((SPOTIFY_CALLBACK_HOST, 0), _SpotifyCallbackHandler)
        server.daemon_threads = True
        server.spotify_event = threading.Event()  # type: ignore[attr-defined]
        server.spotify_code = None  # type: ignore[attr-defined]
        server.spotify_error = None  # type: ignore[attr-defined]
        server.spotify_state = None  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    def _score_search_result(
        self,
        track: MusicTrack,
        query: str,
        item: dict[str, Any],
    ) -> Optional[SpotifyTrackMatch]:
        uri = str(item.get("uri", "") or "")
        name = str(item.get("name", "") or "")
        if not uri.startswith("spotify:track:") or not name:
            return None

        artists = item.get("artists") or []
        artist_names = tuple(
            str(artist.get("name", "") or "").strip()
            for artist in artists
            if isinstance(artist, dict) and str(artist.get("name", "") or "").strip()
        )
        album = item.get("album") or {}
        album_name = str(album.get("name", "") or "")

        title = self._primary_track_title(track)
        normalized_target = self._normalize_match_text(title)
        normalized_name = self._normalize_match_text(name)
        if not normalized_target or not normalized_name:
            return None

        similarity = SequenceMatcher(None, normalized_target, normalized_name).ratio()
        target_tokens = set(normalized_target.split())
        result_tokens = set(normalized_name.split())
        overlap = 0.0
        if target_tokens:
            overlap = len(target_tokens & result_tokens) / len(target_tokens)

        score = (similarity * SPOTIFY_SIMILARITY_WEIGHT) + (overlap * SPOTIFY_OVERLAP_WEIGHT)
        if normalized_target == normalized_name:
            score += SPOTIFY_EXACT_MATCH_BONUS

        series_hint = self._series_hint(track)
        searchable_context = self._normalize_match_text(
            " ".join(artist_names) + " " + album_name
        )
        if series_hint and series_hint in searchable_context:
            score += SPOTIFY_SERIES_HINT_BONUS

        if self._normalize_match_text(query) == normalized_name:
            score += SPOTIFY_QUERY_MATCH_BONUS

        return SpotifyTrackMatch(
            uri=uri,
            name=name,
            artist_names=artist_names,
            album_name=album_name,
            score=min(score, 1.0),
            query_used=query,
        )

    def _build_search_queries(self, track: MusicTrack) -> list[str]:
        title = self._primary_track_title(track)
        series = self._series_hint(track)
        raw_pretty = beautify_track_name(track.track_id)
        raw_title = self._strip_series_suffix(raw_pretty)

        candidates = [
            title,
            raw_title,
            self._cleanup_track_query(track.track_id),
        ]
        if series:
            candidates.insert(1, f"{title} {series}")

        unique_queries: list[str] = []
        seen = set()
        for candidate in candidates:
            cleaned = self._cleanup_track_query(candidate)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique_queries.append(cleaned)
        return unique_queries

    @staticmethod
    def _cleanup_track_query(value: str) -> str:
        cleaned = (value or "").replace("_", " ").strip()
        cleaned = " ".join(cleaned.split())
        if cleaned.lower().startswith("bgm "):
            cleaned = cleaned[4:].strip()
        return cleaned

    def _primary_track_title(self, track: MusicTrack) -> str:
        display_name = track.display_name or beautify_track_name(track.track_id)
        stripped = self._strip_series_suffix(display_name)
        return stripped or self._cleanup_track_query(track.track_id)

    @staticmethod
    def _strip_series_suffix(value: str) -> str:
        cleaned = (value or "").strip()
        if cleaned.endswith("]") and "[" in cleaned:
            return cleaned.rsplit("[", 1)[0].strip(" -")
        return cleaned

    def _series_hint(self, track: MusicTrack) -> str:
        display_name = track.display_name or beautify_track_name(track.track_id)
        if display_name.endswith("]") and "[" in display_name:
            return self._normalize_match_text(
                display_name.rsplit("[", 1)[-1].rstrip("]")
            )
        return ""

    @staticmethod
    def _normalize_match_text(value: str) -> str:
        cleaned = []
        for char in (value or "").lower():
            if char.isalnum():
                cleaned.append(char)
            else:
                cleaned.append(" ")
        return " ".join("".join(cleaned).split())

    @staticmethod
    def _display_track_name(track: MusicTrack) -> str:
        return track.display_name or beautify_track_name(track.track_id)

    def _build_api_error(self, error: urllib.error.HTTPError) -> SpotifyApiError:
        body = ""
        try:
            body = error.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""

        message = f"Spotify request failed ({error.code})."
        retry_after = error.headers.get("Retry-After") if error.headers else None

        if body:
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    error_obj = payload.get("error")
                    if isinstance(error_obj, dict):
                        detail = error_obj.get("message") or error_obj.get("status")
                        if detail:
                            message = f"Spotify request failed ({error.code}): {detail}"
                    elif payload.get("error_description"):
                        message = (
                            f"Spotify request failed ({error.code}): "
                            f"{payload['error_description']}"
                        )
                    elif payload.get("error"):
                        message = f"Spotify request failed ({error.code}): {payload['error']}"
            except json.JSONDecodeError:
                body = body.strip()
                if body:
                    message = f"Spotify request failed ({error.code}): {body}"

        if retry_after:
            message += f" Retry after {retry_after} seconds."

        return SpotifyApiError(message, status_code=error.code)
