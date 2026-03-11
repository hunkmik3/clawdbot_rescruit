"""Job execution pipeline.

Orchestrates the full flow:
1. update status → running
2. for each platform → fetch candidates via Apify
3. normalize → deduplicate → save results
"""

from typing import Any

from app.models.schemas import Candidate
from app.services.apify_client import ApifyClient
from app.services.cross_platform import enrich_candidates_cross_platform
from app.services.job_store import (
    list_job_records,
    load_job,
    save_job,
    update_job_status,
)
from app.services.normalize import normalize_candidate

HISTORICAL_FETCH_MULTIPLIER = 3
HISTORICAL_FETCH_MAX_ITEMS = 300


# ── Actor-input builders ─────────────────────────────────────────────────


def _safe_max_items(raw_value: Any, *, default: int = 20) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = default
    return max(1, value)


def _get_requested_max_items(job_request: dict[str, Any]) -> int:
    return _safe_max_items(job_request.get("max_items_per_platform", 20), default=20)


def _get_effective_max_items(job_request: dict[str, Any]) -> int:
    requested = _get_requested_max_items(job_request)
    return _safe_max_items(
        job_request.get("effective_max_items_per_platform", requested),
        default=requested,
    )


def _build_artstation_input(job_request: dict[str, Any]) -> dict[str, Any]:
    """Build input for contacts-api/artstation-email-scraper-fast-advanced-and-cheapest."""
    keywords = job_request.get("keywords", [])
    location = job_request.get("location")
    max_items = _get_effective_max_items(job_request)

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
    max_items = _get_effective_max_items(job_request)

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
    max_items = _get_effective_max_items(job_request)

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
    max_items = _get_effective_max_items(job_request)

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
    max_items = _get_effective_max_items(job_request)

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

    requested_max_items = _get_requested_max_items(request)
    exclude_previously_scanned = bool(request.get("exclude_previously_scanned", True))
    historical_candidate_keys: set[str] = set()
    effective_max_items = requested_max_items
    if exclude_previously_scanned:
        historical_candidate_keys = _load_historical_candidate_keys(job_id, request)
        if historical_candidate_keys:
            effective_max_items = min(
                HISTORICAL_FETCH_MAX_ITEMS,
                requested_max_items * HISTORICAL_FETCH_MULTIPLIER,
            )
    runtime_request = dict(request)
    runtime_request["effective_max_items_per_platform"] = effective_max_items
    outputs["historical_seed"] = {
        "enabled": exclude_previously_scanned,
        "existing_candidates": len(historical_candidate_keys),
        "requested_max_items_per_platform": requested_max_items,
        "effective_max_items_per_platform": effective_max_items,
    }
    if exclude_previously_scanned and effective_max_items > requested_max_items:
        logger.info(
            "[Pipeline] Historical dedup detected %s existing candidates. "
            "Increasing fetch window from %s to %s per platform.",
            len(historical_candidate_keys),
            requested_max_items,
            effective_max_items,
        )

    for platform in platforms:
        platform_lower = platform.lower()
        items: list[dict] = []

        try:
            # ── ArtStation: use free Playwright scraper ──
            if platform_lower == "artstation":
                from app.services.artstation_scraper import scrape_artstation
                items = scrape_artstation(
                    keywords=runtime_request.get("keywords", []),
                    location=runtime_request.get("location", ""),
                    max_items=_get_effective_max_items(runtime_request),
                )
            # ── Twitter/X: use free scraper + Auto Deep Scan ──
            elif platform_lower == "x":
                from app.services.twitter_scraper import scrape_twitter, scrape_twitter_connections

                items = scrape_twitter(
                    keywords=runtime_request.get("keywords", []),
                    location=runtime_request.get("location", ""),
                    max_items=_get_effective_max_items(runtime_request),
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
                        raw_keywords = runtime_request.get("keywords", [])
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
                actor_input = _build_actor_input(runtime_request, platform_lower)
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

        # Cross-platform enrichment: fetch linked profiles from other platforms
        enriched, enrichment_stats = enrich_candidates_cross_platform(
            deduped, platforms
        )

        fresh_candidates = enriched
        removed_historical = 0
        if exclude_previously_scanned:
            fresh_candidates, removed_historical = _exclude_candidates_seen_before(
                enriched, historical_candidate_keys
            )

        trimmed_to_request = 0
        if (
            exclude_previously_scanned
            and historical_candidate_keys
            and effective_max_items > requested_max_items
        ):
            max_total = requested_max_items * max(len(platforms), 1)
            if len(fresh_candidates) > max_total:
                trimmed_to_request = len(fresh_candidates) - max_total
                fresh_candidates = fresh_candidates[:max_total]

        if enrichment_stats["total_enriched"] > 0:
            outputs["cross_platform_enrichment"] = enrichment_stats
            logger.info(
                f"[Pipeline] Cross-platform enrichment: "
                f"{enrichment_stats['total_enriched']} candidates enriched"
            )
        if exclude_previously_scanned and (removed_historical > 0 or trimmed_to_request > 0):
            outputs["historical_dedup"] = {
                "removed_existing_candidates": removed_historical,
                "trimmed_after_backfill": trimmed_to_request,
                "final_candidates": len(fresh_candidates),
            }

        data["outputs"] = outputs
        data["candidates"] = [candidate.model_dump() for candidate in fresh_candidates]
        data["status"] = "succeeded"
        data["error"] = None
        save_job(job_id, data)
    except Exception as exc:  # noqa: BLE001
        data = load_job(job_id)
        data["status"] = "failed"
        data["error"] = str(exc)
        save_job(job_id, data)



def _normalize_identity(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return normalized.rstrip("/")


def _candidate_identity_key(candidate: Candidate) -> str | None:
    for value in (
        candidate.source_url,
        candidate.linkedin_url,
        candidate.artstation_url,
        candidate.x_url,
        candidate.instagram_url,
        candidate.behance_url,
        candidate.portfolio_url,
    ):
        normalized = _normalize_identity(value)
        if normalized:
            return f"url:{normalized}"

    name = _normalize_identity(candidate.full_name)
    platform = _normalize_identity(candidate.source_platform)
    if name and platform:
        return f"name:{name}|platform:{platform}"
    if name:
        return f"name:{name}"
    return None


def _candidate_identity_key_from_raw(raw_candidate: dict[str, Any]) -> str | None:
    for field in (
        "source_url",
        "linkedin_url",
        "artstation_url",
        "x_url",
        "instagram_url",
        "behance_url",
        "portfolio_url",
    ):
        normalized = _normalize_identity(raw_candidate.get(field))
        if normalized:
            return f"url:{normalized}"

    name = _normalize_identity(raw_candidate.get("full_name"))
    platform = _normalize_identity(raw_candidate.get("source_platform"))
    if name and platform:
        return f"name:{name}|platform:{platform}"
    if name:
        return f"name:{name}"
    return None


def _request_signature(request_payload: dict[str, Any]) -> tuple[tuple[str, ...], str]:
    raw_keywords = request_payload.get("keywords") or []
    keywords = tuple(
        sorted(
            {
                keyword.strip().lower()
                for keyword in raw_keywords
                if isinstance(keyword, str) and keyword.strip()
            }
        )
    )
    location = _normalize_identity(request_payload.get("location")) or ""
    return keywords, location


def _load_historical_candidate_keys(
    current_job_id: str, current_request: dict[str, Any]
) -> set[str]:
    seen_keys: set[str] = set()
    current_signature = _request_signature(current_request)

    for record in list_job_records():
        if record.get("job_id") == current_job_id:
            continue
        if record.get("status") != "succeeded":
            continue
        if _request_signature(record.get("request") or {}) != current_signature:
            continue

        for raw_candidate in record.get("candidates", []):
            if not isinstance(raw_candidate, dict):
                continue
            key = _candidate_identity_key_from_raw(raw_candidate)
            if key:
                seen_keys.add(key)
    return seen_keys


def _exclude_candidates_seen_before(
    candidates: list[Candidate], historical_keys: set[str]
) -> tuple[list[Candidate], int]:
    if not historical_keys:
        return candidates, 0

    filtered: list[Candidate] = []
    removed = 0
    seen_keys = set(historical_keys)

    for candidate in candidates:
        key = _candidate_identity_key(candidate)
        if key and key in seen_keys:
            removed += 1
            continue

        filtered.append(candidate)
        if key:
            seen_keys.add(key)

    return filtered, removed


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Remove duplicate candidates within the same job."""
    seen: set[str] = set()
    deduped: list[Candidate] = []

    for candidate in candidates:
        key = _candidate_identity_key(candidate)
        if key:
            if key in seen:
                continue
            seen.add(key)
        deduped.append(candidate)

    return deduped
