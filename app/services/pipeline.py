"""Job execution pipeline.

Orchestrates the full flow:
1. update status → running
2. for each platform → fetch candidates via Apify
3. normalize → deduplicate → save results
"""

from typing import Any

from app.models.schemas import Candidate
from app.services.apify_client import ApifyClient
from app.services.job_store import load_job, save_job, update_job_status
from app.services.normalize import normalize_candidate


# ── Actor-input builders ─────────────────────────────────────────────────


def _build_artstation_input(job_request: dict[str, Any]) -> dict[str, Any]:
    """Build input for contacts-api/artstation-email-scraper-fast-advanced-and-cheapest."""
    keywords = job_request.get("keywords", [])
    location = job_request.get("location")
    max_items = int(job_request.get("max_items_per_platform", 20))

    actor_input: dict[str, Any] = {
        "keywords": keywords,
        "maxItems": max_items,
        "emailDomains": ["@gmail.com"],
    }

    if location:
        actor_input["location"] = location

    return actor_input


def _build_linkedin_input(job_request: dict[str, Any]) -> dict[str, Any]:
    """Build input for harvestapi/linkedin-profile-search.

    Documented fields:
      searchQuery   – general fuzzy search query
      currentJobTitles – list of exact job titles
      locations     – list of location strings
      maxItems      – max profiles to scrape (0 = all)
      startPage     – page to start from (default 1)
      takePages     – number of pages to scrape (max 100)
      profileScraperMode – "Short" | "Full" | "Full + email search"
    """
    keywords = job_request.get("keywords", [])
    location = job_request.get("location")
    max_items = int(job_request.get("max_items_per_platform", 20))

    search_query = " ".join(keywords) if keywords else ""

    actor_input: dict[str, Any] = {
        "searchQuery": search_query,
        "currentJobTitles": keywords,
        "maxItems": max_items,
        "profileScraperMode": "Full",
        "startPage": 1,
    }

    if location:
        actor_input["locations"] = [location]

    return actor_input


def _build_instagram_input(job_request: dict[str, Any]) -> dict[str, Any]:
    """Build input for apify/instagram-scraper.

    We use 'user' search type. By combining keywords and location
    (e.g., '2D animator Vietnam'), the Instagram search engine 
    returns highly relevant profiles containing these terms in 
    their bio or name.
    """
    keywords = job_request.get("keywords", [])
    location = job_request.get("location", "")
    max_items = int(job_request.get("max_items_per_platform", 20))

    # Combine keywords and location
    search_parts = keywords.copy()
    if location:
        search_parts.append(location)

    search_query = " ".join(search_parts) if search_parts else "artist"

    return {
        "search": search_query,
        "searchType": "user",
        "searchLimit": max_items,
        "resultsType": "details",
        "resultsLimit": 1,
    }

def _build_x_input(job_request: dict[str, Any]) -> dict[str, Any]:
    """Build input for web.harvester/twitter-scraper.
    Uses 'userQueries' to search for user profiles on X/Twitter.
    """
    keywords = job_request.get("keywords", [])
    location = job_request.get("location", "")
    max_items = int(job_request.get("max_items_per_platform", 20))

    # Combine keywords + location into user search queries
    search_queries = []
    for kw in keywords:
        query = f"{kw} {location}".strip() if location else kw
        search_queries.append(query)

    if not search_queries:
        search_queries.append(f"artist {location}".strip())

    return {
        "userQueries": search_queries,
        "profilesDesired": max_items,
        "tweetsDesired": 5,
        "includeUserInfo": True,
    }


def _build_generic_input(job_request: dict[str, Any], platform: str) -> dict[str, Any]:
    """Build a generic Apify actor input."""
    keywords = job_request.get("keywords", [])
    location = job_request.get("location")
    max_items = int(job_request.get("max_items_per_platform", 20))

    actor_input: dict[str, Any] = {
        "searchTerms": keywords,
        "maxItems": max_items,
        "platform": platform,
    }
    if location:
        actor_input["location"] = location

    return actor_input


def _build_actor_input(job_request: dict[str, Any], platform: str) -> dict[str, Any]:
    """Build the appropriate actor input based on platform."""
    # If caller provided a raw actor input for this platform, use it directly.
    raw_inputs: dict[str, Any] = job_request.get("actor_inputs") or {}
    if platform in raw_inputs:
        return raw_inputs[platform]

    builders = {
        "artstation": _build_artstation_input,
        "linkedin": _build_linkedin_input,
        "instagram": _build_instagram_input,
        "x": _build_x_input,
    }

    builder = builders.get(platform.lower())
    if builder:
        return builder(job_request)

    return _build_generic_input(job_request, platform)


# ── Job runner ───────────────────────────────────────────────────────────


def run_job(job_id: str) -> None:
    """Execute a scraping job across all requested platforms."""
    update_job_status(job_id, "running")
    data = load_job(job_id)
    request = data.get("request", {})
    platforms = request.get("platforms", [])
    actor_overrides: dict[str, str] = request.get("actor_overrides", {}) or {}

    client = ApifyClient()
    all_candidates: list[Candidate] = []
    outputs: dict[str, Any] = {}

    import logging
    logger = logging.getLogger(__name__)

    for platform in platforms:
        platform_lower = platform.lower()
        items: list[dict] = []

        try:
            # ── ArtStation: use free Playwright scraper ──
            if platform_lower == "artstation":
                from app.services.artstation_scraper import scrape_artstation
                items = scrape_artstation(
                    keywords=request.get("keywords", []),
                    location=request.get("location", ""),
                    max_items=int(request.get("max_items_per_platform", 20)),
                )
            # ── Twitter/X: use free scraper + Auto Deep Scan ──
            elif platform_lower == "x":
                from app.services.twitter_scraper import scrape_twitter, scrape_twitter_connections

                items = scrape_twitter(
                    keywords=request.get("keywords", []),
                    location=request.get("location", ""),
                    max_items=int(request.get("max_items_per_platform", 20)),
                )

                # ── AUTO DEEP SCAN ──
                # Tìm profile có followers nhiều nhất → quét connections
                if items:
                    best_profile = None
                    max_followers = 0
                    for item in items:
                        user = item.get("user", {})
                        fc = user.get("followers_count") or 0
                        if fc > max_followers:
                            max_followers = fc
                            best_profile = user

                    if best_profile and max_followers >= 10:
                        target_username = best_profile.get("screen_name", "")
                        logger.info(
                            f"[Auto Deep Scan] Đào sâu @{target_username} "
                            f"({max_followers} followers)..."
                        )

                        # Quét cả followers và following
                        deep_items: list[dict] = []
                        for conn_type in ["followers", "following"]:
                            try:
                                connections = scrape_twitter_connections(
                                    screen_name=target_username,
                                    connection_type=conn_type,
                                    max_items=15,
                                )
                                deep_items.extend(connections)
                                logger.info(
                                    f"[Auto Deep Scan] {conn_type}: "
                                    f"tìm thấy {len(connections)} profiles"
                                )
                            except Exception as deep_exc:
                                logger.warning(
                                    f"[Auto Deep Scan] Lỗi {conn_type}: {deep_exc}"
                                )

                        # Lọc connections theo keywords gốc - linh hoạt hơn
                        # VD: "2D animator" → match "2d", "animator", "animation", "animate"
                        raw_keywords = request.get("keywords", [])
                        keywords_lower = []
                        for kw in raw_keywords:
                            keywords_lower.append(kw.lower())  # full phrase
                            for word in kw.lower().split():
                                if len(word) >= 3:  # bỏ từ quá ngắn
                                    keywords_lower.append(word)
                        keywords_lower = list(set(keywords_lower))

                        filtered_deep = []
                        for di in deep_items:
                            user = di.get("user", {})
                            bio = (user.get("description") or "").lower()
                            name = (user.get("name") or "").lower()
                            title = (user.get("title") or "").lower()
                            # Giữ lại nếu bio, tên, hoặc title chứa bất kỳ keyword nào
                            if any(kw in bio or kw in name or kw in title for kw in keywords_lower):
                                filtered_deep.append(di)

                        # Nếu filter quá strict → giữ lại tất cả deep items
                        if not filtered_deep and deep_items:
                            logger.info("[Auto Deep Scan] Không có kết quả sau filter → giữ tất cả connections")
                            filtered_deep = deep_items

                        logger.info(
                            f"[Auto Deep Scan] Sau lọc keyword: "
                            f"{len(filtered_deep)}/{len(deep_items)} profiles phù hợp"
                        )

                        items.extend(filtered_deep)
                        outputs["x_deep_scan"] = {
                            "target": f"@{target_username}",
                            "target_followers": max_followers,
                            "raw_connections": len(deep_items),
                            "filtered_relevant": len(filtered_deep),
                        }

            else:
                # ── Other platforms: use Apify ──
                actor_input = _build_actor_input(request, platform_lower)
                items = client.run_actor_and_fetch_items(
                    platform=platform_lower,
                    actor_input=actor_input,
                    actor_id_override=actor_overrides.get(platform_lower),
                )

        except Exception as platform_exc:  # noqa: BLE001
            logger.error(f"[Pipeline] Platform '{platform_lower}' failed: {platform_exc}")
            outputs[platform_lower] = {"count": 0, "error": str(platform_exc)}
            continue

        outputs[platform_lower] = {
            "count": len(items),
            "sample": items[:2],
        }

        for item in items:
            try:
                candidate = normalize_candidate(item=item, platform=platform_lower)
                all_candidates.append(candidate)
            except Exception as exc:  # noqa: BLE001
                outputs.setdefault(platform_lower, {}).setdefault("normalize_errors", []).append(str(exc))

    try:
        deduped = _dedupe_candidates(all_candidates)
        data["outputs"] = outputs
        data["candidates"] = [candidate.model_dump() for candidate in deduped]
        data["status"] = "succeeded"
        data["error"] = None
        save_job(job_id, data)
    except Exception as exc:  # noqa: BLE001
        data = load_job(job_id)
        data["status"] = "failed"
        data["error"] = str(exc)
        save_job(job_id, data)



def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Remove duplicate candidates based on URL or name+platform."""
    seen: set[str] = set()
    deduped: list[Candidate] = []

    for candidate in candidates:
        key = (
            candidate.source_url
            or candidate.linkedin_url
            or candidate.artstation_url
            or candidate.portfolio_url
            or (candidate.full_name or "") + "|" + (candidate.source_platform or "")
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    return deduped
