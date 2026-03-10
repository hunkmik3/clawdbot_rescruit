"""Cross-platform profile enrichment.

After initial scraping, discovers links to other platforms in candidate
profiles and fetches additional data to enrich candidates.

Supported enrichment:
- ArtStation profiles (Playwright - free): skills, software, email, social links
- Twitter/X profiles (Playwright - free): bio, location, followers
"""

import logging
import re
import urllib.parse
from typing import Any

from app.models.schemas import Candidate, WorkSample

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

MAX_ENRICHMENTS_PER_PLATFORM = 10


# ── URL parsers ──────────────────────────────────────────────────────────


def _extract_artstation_username(url: str) -> str | None:
    m = re.search(r"artstation\.com/([a-zA-Z0-9_.-]+)", url)
    if m and m.group(1).lower() not in (
        "artwork", "search", "jobs", "learning", "blogs",
        "contests", "api", "users", "www",
    ):
        return m.group(1)
    return None


def _extract_twitter_username(url: str) -> str | None:
    m = re.search(r"(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)", url)
    if m and m.group(1).lower() not in (
        "search", "home", "explore", "settings", "i",
        "hashtag", "intent", "share",
    ):
        return m.group(1)
    return None


def _extract_instagram_username(url: str) -> str | None:
    m = re.search(r"instagram\.com/([a-zA-Z0-9_.]+)", url)
    if m and m.group(1).lower() not in (
        "p", "explore", "reels", "stories", "accounts", "reel",
    ):
        return m.group(1)
    return None


# ── Batch profile fetchers ───────────────────────────────────────────────


def _fetch_artstation_profiles(usernames: list[str]) -> dict[str, dict]:
    """Fetch multiple ArtStation profiles in a single browser session."""
    results: dict[str, dict] = {}
    if not usernames:
        return results

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            # Visit homepage first to pass Cloudflare
            try:
                page.goto(
                    "https://www.artstation.com/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"[CrossPlatform] ArtStation homepage failed: {e}")
                browser.close()
                return results

            for username in usernames[:MAX_ENRICHMENTS_PER_PLATFORM]:
                try:
                    api_url = (
                        f"https://www.artstation.com/users/"
                        f"{urllib.parse.quote(username)}.json"
                    )
                    raw = page.evaluate(
                        """async (url) => {
                            try {
                                const resp = await fetch(url, {
                                    headers: {'Accept': 'application/json'}
                                });
                                if (!resp.ok) return null;
                                return await resp.json();
                            } catch(e) { return null; }
                        }""",
                        api_url,
                    )
                    if raw and isinstance(raw, dict):
                        results[username] = raw
                        logger.info(
                            f"[CrossPlatform] ArtStation: fetched {username}"
                        )
                except Exception as e:
                    logger.debug(
                        f"[CrossPlatform] ArtStation fetch failed for {username}: {e}"
                    )

            browser.close()
    except Exception as e:
        logger.warning(f"[CrossPlatform] ArtStation browser error: {e}")

    return results


def _fetch_twitter_profiles(screen_names: list[str]) -> dict[str, dict]:
    """Fetch multiple Twitter profiles in a single browser session."""
    results: dict[str, dict] = {}
    if not screen_names:
        return results

    from playwright.sync_api import sync_playwright
    from app.services.twitter_scraper import (
        _create_browser_context,
        _enrich_user_profile,
    )

    try:
        with sync_playwright() as p:
            browser, context = _create_browser_context(p)

            for sn in screen_names[:MAX_ENRICHMENTS_PER_PLATFORM]:
                try:
                    profile = _enrich_user_profile(context, sn)
                    if profile and (
                        profile.get("description") or profile.get("followers_count")
                    ):
                        profile["screen_name"] = sn
                        results[sn] = profile
                        logger.info(f"[CrossPlatform] Twitter: fetched @{sn}")
                except Exception as e:
                    logger.debug(
                        f"[CrossPlatform] Twitter fetch failed for @{sn}: {e}"
                    )

            browser.close()
    except Exception as e:
        logger.warning(f"[CrossPlatform] Twitter browser error: {e}")

    return results


# ── Merge logic ──────────────────────────────────────────────────────────


def _merge_artstation_data(candidate: Candidate, profile: dict) -> Candidate:
    """Merge ArtStation profile data into an existing candidate."""
    data = candidate.model_dump()

    # Email
    if not data.get("email") and profile.get("public_email"):
        data["email"] = profile["public_email"]

    # Bio
    if not data.get("bio"):
        data["bio"] = profile.get("summary") or profile.get("headline")

    # Skills
    existing_skills = set(s.lower() for s in (data.get("skills") or []))
    for s in (profile.get("skills") or []):
        name = s.get("name") if isinstance(s, dict) else str(s)
        if name and name.lower() not in existing_skills:
            data.setdefault("skills", []).append(name)
            existing_skills.add(name.lower())

    # Software
    existing_sw = set(s.lower() for s in (data.get("software") or []))
    for s in (profile.get("software_items") or []):
        name = s.get("name") if isinstance(s, dict) else str(s)
        if name and name.lower() not in existing_sw:
            data.setdefault("software", []).append(name)
            existing_sw.add(name.lower())

    # Social links from ArtStation
    for link in (profile.get("social_links") or []):
        url = link.get("url", "")
        url_lower = url.lower()
        if "linkedin" in url_lower and not data.get("linkedin_url"):
            data["linkedin_url"] = url
        elif ("twitter" in url_lower or "x.com" in url_lower) and not data.get("x_url"):
            data["x_url"] = url
        elif "instagram" in url_lower and not data.get("instagram_url"):
            data["instagram_url"] = url
        elif "behance" in url_lower and not data.get("behance_url"):
            data["behance_url"] = url
        elif url and not data.get("portfolio_url"):
            data["portfolio_url"] = url

    # ArtStation URL
    username = profile.get("username")
    if not data.get("artstation_url") and username:
        data["artstation_url"] = f"https://www.artstation.com/{username}"

    # Followers (keep higher count)
    as_followers = profile.get("followers_count")
    if as_followers and (not data.get("followers_count") or as_followers > data["followers_count"]):
        data["followers_count"] = as_followers

    # Location
    if not data.get("location"):
        parts = [profile.get("city"), profile.get("country")]
        loc = ", ".join(p for p in parts if p)
        if loc:
            data["location"] = loc

    # Track enrichment source
    raw = data.get("raw") or {}
    raw.setdefault("cross_platform", {})["artstation"] = {
        "username": username,
        "skills_added": len(data.get("skills", [])) - len(candidate.skills),
        "software_added": len(data.get("software", [])) - len(candidate.software),
    }
    data["raw"] = raw

    return Candidate(**data)


def _merge_twitter_data(candidate: Candidate, profile: dict) -> Candidate:
    """Merge Twitter profile data into an existing candidate."""
    data = candidate.model_dump()

    if not data.get("bio") and profile.get("description"):
        data["bio"] = profile["description"]

    if not data.get("location") and profile.get("location"):
        data["location"] = profile["location"]

    if not data.get("followers_count") and profile.get("followers_count"):
        data["followers_count"] = profile["followers_count"]

    sn = profile.get("screen_name")
    if not data.get("x_url") and sn:
        data["x_url"] = f"https://x.com/{sn}"

    # Extract additional links from Twitter bio
    bio = profile.get("description") or ""
    if bio:
        # Clean newlines in URLs
        clean_bio = re.sub(r"(https?://)\s+", r"\1", bio).lower()

        if not data.get("linkedin_url"):
            m = re.search(r"linkedin\.com/in/([a-zA-Z0-9_-]+)", clean_bio)
            if m:
                data["linkedin_url"] = f"https://www.linkedin.com/in/{m.group(1)}"

        if not data.get("instagram_url"):
            m = re.search(r"instagram\.com/([a-zA-Z0-9_.]+)", clean_bio)
            if m:
                data["instagram_url"] = f"https://www.instagram.com/{m.group(1)}"

        if not data.get("artstation_url"):
            m = re.search(r"artstation\.com/([a-zA-Z0-9_.-]+)", clean_bio)
            if m and m.group(1).lower() not in ("artwork", "search"):
                data["artstation_url"] = f"https://www.artstation.com/{m.group(1)}"

        if not data.get("portfolio_url"):
            m = re.search(
                r"https?://(?!t\.co|twitter\.com|x\.com|linkedin\.com|"
                r"instagram\.com|facebook\.com|t\.me)"
                r"([a-zA-Z0-9.-]+\.[a-z]{2,}/?[^\s]*)",
                clean_bio,
            )
            if m:
                data["portfolio_url"] = m.group(0)

    # Track enrichment source
    raw = data.get("raw") or {}
    raw.setdefault("cross_platform", {})["x"] = {
        "screen_name": sn,
        "bio_found": bool(profile.get("description")),
        "location_found": bool(profile.get("location")),
    }
    data["raw"] = raw

    return Candidate(**data)


# ── Main enrichment function ─────────────────────────────────────────────


def enrich_candidates_cross_platform(
    candidates: list[Candidate],
    scraped_platforms: list[str],
) -> tuple[list[Candidate], dict[str, Any]]:
    """
    Scan candidates for cross-platform links and fetch additional data.

    Only fetches from platforms that weren't already in the scraping job,
    to avoid duplicate work.

    Returns (enriched_candidates, enrichment_stats).
    """
    stats: dict[str, Any] = {
        "artstation_fetched": 0,
        "x_fetched": 0,
        "total_enriched": 0,
        "links_discovered": 0,
    }

    scraped_lower = {p.lower() for p in scraped_platforms}

    # Collect cross-platform URLs to fetch
    # (candidate_index, username)
    artstation_to_fetch: list[tuple[int, str]] = []
    twitter_to_fetch: list[tuple[int, str]] = []

    seen_as_usernames: set[str] = set()
    seen_tw_usernames: set[str] = set()

    # Pre-populate seen sets from existing candidates
    for c in candidates:
        if c.artstation_url:
            u = _extract_artstation_username(c.artstation_url)
            if u:
                seen_as_usernames.add(u.lower())
        if c.x_url:
            u = _extract_twitter_username(c.x_url)
            if u:
                seen_tw_usernames.add(u.lower())

    for i, candidate in enumerate(candidates):
        # Discover ArtStation links to fetch
        if "artstation" not in scraped_lower:
            as_url = candidate.artstation_url
            if as_url:
                username = _extract_artstation_username(as_url)
                if username and username.lower() not in seen_as_usernames:
                    artstation_to_fetch.append((i, username))
                    seen_as_usernames.add(username.lower())
                    stats["links_discovered"] += 1

            # Also check bio for ArtStation links
            bio = candidate.bio or ""
            if not as_url and "artstation" in bio.lower():
                username = _extract_artstation_username(bio)
                if username and username.lower() not in seen_as_usernames:
                    artstation_to_fetch.append((i, username))
                    seen_as_usernames.add(username.lower())
                    stats["links_discovered"] += 1

        # Discover Twitter/X links to fetch
        if "x" not in scraped_lower:
            x_url = candidate.x_url
            if x_url:
                username = _extract_twitter_username(x_url)
                if username and username.lower() not in seen_tw_usernames:
                    twitter_to_fetch.append((i, username))
                    seen_tw_usernames.add(username.lower())
                    stats["links_discovered"] += 1

            # Also check bio for Twitter links
            bio = candidate.bio or ""
            if not x_url and ("twitter.com" in bio.lower() or "x.com" in bio.lower()):
                username = _extract_twitter_username(bio)
                if username and username.lower() not in seen_tw_usernames:
                    twitter_to_fetch.append((i, username))
                    seen_tw_usernames.add(username.lower())
                    stats["links_discovered"] += 1

    total = len(artstation_to_fetch) + len(twitter_to_fetch)
    if total == 0:
        logger.info("[CrossPlatform] No cross-platform links found to enrich.")
        return candidates, stats

    logger.info(
        f"[CrossPlatform] Found {total} cross-platform links to enrich "
        f"(ArtStation: {len(artstation_to_fetch)}, "
        f"Twitter: {len(twitter_to_fetch)})"
    )

    enriched = list(candidates)

    # Fetch and merge ArtStation profiles
    if artstation_to_fetch:
        usernames = [u for _, u in artstation_to_fetch]
        profiles = _fetch_artstation_profiles(usernames)
        for idx, username in artstation_to_fetch:
            if username in profiles:
                enriched[idx] = _merge_artstation_data(
                    enriched[idx], profiles[username]
                )
                stats["artstation_fetched"] += 1
                stats["total_enriched"] += 1

    # Fetch and merge Twitter profiles
    if twitter_to_fetch:
        screen_names = [u for _, u in twitter_to_fetch]
        profiles = _fetch_twitter_profiles(screen_names)
        for idx, username in twitter_to_fetch:
            if username in profiles:
                enriched[idx] = _merge_twitter_data(
                    enriched[idx], profiles[username]
                )
                stats["x_fetched"] += 1
                stats["total_enriched"] += 1

    logger.info(
        f"[CrossPlatform] Enrichment complete: "
        f"{stats['total_enriched']} candidates enriched"
    )

    return enriched, stats
