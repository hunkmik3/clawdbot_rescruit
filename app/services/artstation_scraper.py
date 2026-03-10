"""ArtStation scraper using Playwright to call their API.

Uses browser context to bypass Cloudflare, then fetches JSON API
responses through the browser. Completely free - no Apify costs.
"""

import logging
import urllib.parse
from typing import Any

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def scrape_artstation(
    keywords: list[str],
    location: str = "",
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """
    Search ArtStation users by using Playwright browser to call their API.
    Returns a list of profile dicts ready for normalization.
    """
    query = " ".join(keywords)
    if location:
        query += f" {location}"

    logger.info(f"[ArtStation] Searching: '{query}', max_items={max_items}")

    results: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        try:
            # First visit homepage to pass Cloudflare (retry up to 2 times)
            homepage_loaded = False
            for attempt in range(2):
                try:
                    logger.info(f"[ArtStation] Visiting homepage to pass Cloudflare (attempt {attempt + 1})...")
                    page.goto("https://www.artstation.com/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)
                    homepage_loaded = True
                    break
                except Exception as e:
                    logger.warning(f"[ArtStation] Homepage load attempt {attempt + 1} failed: {e}")
                    if attempt == 0:
                        page.wait_for_timeout(2000)

            if not homepage_loaded:
                logger.error("[ArtStation] Could not load homepage after retries")
                return results

            # Now call the search API via page.evaluate (runs in browser context)
            per_page = min(max_items, 50)
            pages_needed = (max_items + per_page - 1) // per_page

            for page_num in range(1, pages_needed + 1):
                if len(results) >= max_items:
                    break

                encoded_query = urllib.parse.quote(query)
                api_url = (
                    f"https://www.artstation.com/api/v2/search/users.json"
                    f"?query={encoded_query}&page={page_num}&per_page={per_page}"
                )

                logger.info(f"[ArtStation] Fetching page {page_num}...")

                # Use page.evaluate to make fetch request from within the browser
                # Pass URL as argument to avoid JS injection from user query
                raw = page.evaluate("""async (url) => {
                        const resp = await fetch(url, {
                            headers: { 'Accept': 'application/json' }
                        });
                        if (!resp.ok) return { error: resp.status };
                        return await resp.json();
                    }""", api_url)

                if isinstance(raw, dict) and raw.get("error"):
                    logger.warning(f"[ArtStation] API error: {raw['error']}")
                    break

                users = raw.get("data", [])
                total = raw.get("total_count", 0)
                logger.info(f"[ArtStation] Page {page_num}: {len(users)} users (total: {total})")

                if not users:
                    break

                for user in users:
                    if len(results) >= max_items:
                        break
                    profile = _build_profile(user)

                    # Enrich with full profile data
                    username = user.get("username")
                    if username:
                        profile = _enrich_from_full_profile(page, username, profile)

                    results.append(profile)

        except Exception as e:
            logger.error(f"[ArtStation] Fatal error: {e}")
        finally:
            browser.close()

    logger.info(f"[ArtStation] Done. Total profiles: {len(results)}")
    return results


def _build_profile(user: dict[str, Any]) -> dict[str, Any]:
    """Build profile dict from search API result."""
    profile: dict[str, Any] = {
        "full_name": user.get("full_name") or user.get("username"),
        "title": user.get("headline"),
        "location": user.get("location"),
        "artstation_url": user.get("artstation_profile_url")
            or f"https://www.artstation.com/{user.get('username', '')}",
        "source_url": user.get("artstation_profile_url"),
        "followers_count": user.get("followers_count"),
        "bio": user.get("headline"),
        "username": user.get("username"),
        "available_freelance": user.get("available_freelance"),
        "available_full_time": user.get("available_full_time"),
        "project_views_count": user.get("project_views_count"),
        "likes_count": user.get("likes_count"),
    }

    # Top works from sample_projects
    sample_projects = user.get("sample_projects") or []
    top_works = []
    for proj in sample_projects[:5]:
        hash_id = proj.get("hash_id")
        if hash_id:
            top_works.append(f"https://www.artstation.com/artwork/{hash_id}")
    if top_works:
        profile["top_works"] = top_works

    return profile


def _enrich_from_full_profile(page, username: str, profile: dict[str, Any]) -> dict[str, Any]:
    """Fetch user's full profile JSON to get email, skills, social links."""
    try:
        api_url = f"https://www.artstation.com/users/{urllib.parse.quote(username)}.json"
        # Pass URL as argument to avoid JS injection
        raw = page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url, {
                        headers: { 'Accept': 'application/json' }
                    });
                    if (!resp.ok) return null;
                    return await resp.json();
                } catch(e) {
                    return null;
                }
            }""", api_url)

        if not raw or not isinstance(raw, dict):
            return profile

        # Email
        email = raw.get("public_email")
        if email:
            profile["email"] = email

        # Bio / summary
        summary = raw.get("summary") or raw.get("headline")
        if summary:
            profile["bio"] = summary

        # Skills
        skills = raw.get("skills") or []
        if isinstance(skills, list) and skills:
            profile["skills"] = [
                s.get("name") if isinstance(s, dict) else str(s)
                for s in skills[:10]
            ]

        # Social links
        for link in (raw.get("social_links") or []):
            url = link.get("url", "")
            if "linkedin" in url.lower():
                profile["linkedin_url"] = url
            elif "twitter" in url.lower() or "x.com" in url.lower():
                profile["x_url"] = url
            elif "instagram" in url.lower():
                profile["instagram_url"] = url
            elif not profile.get("portfolio_url"):
                profile["portfolio_url"] = url

    except Exception as e:
        logger.debug(f"[ArtStation] Could not enrich {username}: {e}")

    return profile
