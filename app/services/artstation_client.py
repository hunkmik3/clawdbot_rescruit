"""ArtStation client via RapidAPI.

Uses the ArtStation API on RapidAPI marketplace to fetch artist details
and project information.

RapidAPI Host: artstation.p.rapidapi.com
Endpoints used:
  GET /artists/{username_or_id}  → Artist Details
  GET /projects/{project_id}     → Project Details
  GET /artists/{id}/projects     → Projects of an artist
  GET /channels/{channel}/projects → Projects Of Channel (for search)
"""

from typing import Any

import httpx

from app.core.config import settings


class ArtStationClient:
    """Client for ArtStation via RapidAPI."""

    BASE_URL = "https://artstation.p.rapidapi.com"

    def __init__(self) -> None:
        self.api_key = settings.rapidapi_key
        self.timeout = httpx.Timeout(30.0)
        self.headers = {
            "x-rapidapi-host": "artstation.p.rapidapi.com",
            "x-rapidapi-key": self.api_key,
        }

    def _ensure_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("RAPIDAPI_KEY is missing — required for ArtStation API")

    # ── Artist details ──────────────────────────────────────────────────

    def get_artist(self, username: str) -> dict[str, Any] | None:
        """Fetch full artist profile by username or ID."""
        self._ensure_key()
        url = f"{self.BASE_URL}/artists/{username}"

        with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
            try:
                response = client.get(url)
                if response.status_code != 200:
                    return None
                return response.json()
            except Exception:
                return None

    # ── Artist projects ─────────────────────────────────────────────────

    def get_artist_projects(self, username: str, *, page: int = 1) -> list[dict[str, Any]]:
        """Fetch projects for a specific artist."""
        self._ensure_key()
        url = f"{self.BASE_URL}/artists/{username}/projects"
        params = {"page": page}

        with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
            try:
                response = client.get(url, params=params)
                if response.status_code != 200:
                    return []
                data = response.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("data", [])
                return []
            except Exception:
                return []

    # ── Channel/search projects ─────────────────────────────────────────

    def search_projects_by_channel(
        self, channel: str = "community", *, query: str = "", page: int = 1
    ) -> list[dict[str, Any]]:
        """Fetch projects from a channel (can be used for discovery)."""
        self._ensure_key()
        url = f"{self.BASE_URL}/channels/{channel}/projects"
        params: dict[str, Any] = {"page": page}
        if query:
            params["query"] = query

        with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
            try:
                response = client.get(url, params=params)
                if response.status_code != 200:
                    return []
                data = response.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("data", [])
                return []
            except Exception:
                return []

    # ── Combined: discover artists from projects ────────────────────────

    def search_and_fetch_artists(
        self, query: str, *, max_results: int = 20, max_search_pages: int = 3
    ) -> list[dict[str, Any]]:
        """Discover artists by searching projects, then fetch artist profiles.

        Strategy: search projects → extract unique artist usernames →
        fetch full artist profile + their projects.

        Returns a list of enriched dicts:
        {
            "profile": { ... full artist profile ... },
            "projects": [ ... artist projects ... ],
        }
        """
        self._ensure_key()

        # Step 1: Collect unique artist usernames from project search
        seen_usernames: set[str] = set()
        artist_usernames: list[str] = []

        for page in range(1, max_search_pages + 1):
            projects = self.search_projects_by_channel("community", query=query, page=page)
            if not projects:
                break

            for proj in projects:
                # Try to extract artist username from project data
                user = proj.get("user") or {}
                username = user.get("username") or proj.get("username")
                if not username:
                    # Try from permalink: https://www.artstation.com/username/...
                    permalink = proj.get("permalink") or ""
                    if "artstation.com/" in permalink:
                        parts = permalink.replace("https://www.artstation.com/", "").split("/")
                        if parts:
                            username = parts[0]

                if username and username not in seen_usernames:
                    seen_usernames.add(username)
                    artist_usernames.append(username)

                if len(artist_usernames) >= max_results:
                    break

            if len(artist_usernames) >= max_results:
                break

        # Step 2: Fetch full profile + projects for each artist
        enriched: list[dict[str, Any]] = []
        for username in artist_usernames[:max_results]:
            profile = self.get_artist(username)
            if not profile:
                continue

            projects = self.get_artist_projects(username, page=1)

            enriched.append(
                {
                    "profile": profile,
                    "projects": projects[:5],
                }
            )

        return enriched
