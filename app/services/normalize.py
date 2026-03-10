"""Normalize raw platform data into the unified Candidate schema.

Each platform returns different JSON structures. This module maps them all
into a single `Candidate` model so downstream code can treat them uniformly.
"""

from typing import Any

from app.models.schemas import Candidate, WorkSample


# ── Helpers ──────────────────────────────────────────────────────────────


def first_non_empty(data: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _estimate_years_exp(item: dict[str, Any]) -> float | None:
    value = item.get("years_exp") or item.get("years_experience")
    if isinstance(value, (int, float)):
        return float(value)

    text = item.get("experience")
    if isinstance(text, str):
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            try:
                return float(int(digits))
            except ValueError:
                return None

    return None


# ── Router ───────────────────────────────────────────────────────────────


def normalize_candidate(item: dict[str, Any], platform: str) -> Candidate:
    """Dispatch to the appropriate platform normalizer."""
    normalizer = _NORMALIZERS.get(platform.lower(), _normalize_generic)
    return normalizer(item, platform)


# ── ArtStation ───────────────────────────────────────────────────────────


def _normalize_artstation(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize an ArtStation result.

    Handles two possible formats:
    1. Apify email scraper output (flat dict with email, title, snippet, sourceUrl)
    2. Enriched profile format (nested profile + projects dicts)
    """
    # ── Check if this is enriched format (profile + projects)
    profile = item.get("profile")
    if profile and isinstance(profile, dict):
        return _normalize_artstation_enriched(item, platform)

    # ── Flat format from Apify email scraper
    # Raw fields: network, keyword, title (page name), description (bio), url, email
    raw_title = first_non_empty(item, ["title"])
    email = first_non_empty(item, ["email", "contactEmail", "public_email"])
    source_url = first_non_empty(item, ["url", "sourceUrl", "source_url", "profileUrl", "link"])
    description = first_non_empty(item, ["description", "snippet", "bio", "headline"])
    location = first_non_empty(item, ["location", "city", "country"])

    # The "title" field is often the page title (e.g. "Ramona Harriott" or "Resume")
    # Use it as full_name if it looks like a real name (not generic page titles)
    generic_titles = {"resume", "about", "portfolio", "home", "contact"}
    full_name = None
    if raw_title and raw_title.lower().strip() not in generic_titles:
        # Remove common suffixes like " - Resume", " Portfolio"
        name = raw_title
        for suffix in [" - Resume", " Portfolio", " - Portfolio", " - About"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        full_name = name.strip() if name.strip() else None

    # If no name, try to extract from URL (username)
    if not full_name and source_url and "artstation.com" in source_url:
        parts = source_url.replace("https://", "").replace("http://", "").split("/")
        for part in parts:
            if part and part not in ("www.artstation.com", "artstation.com"):
                if "." not in part:  # skip subdomains like "user.artstation.com"
                    full_name = part
                    break

    # Extract job title from description (first sentence before |, ., or email)
    job_title = None
    if description:
        # Try to get first meaningful part of description
        for sep in ["|", ".", "—", "-"]:
            if sep in description:
                job_title = description.split(sep)[0].strip()
                break
        if not job_title:
            job_title = description[:100].strip()

    artstation_url = None
    if source_url and "artstation.com" in source_url:
        artstation_url = source_url

    # Extract cross-platform links
    linkedin_url = first_non_empty(item, ["linkedin_url"])
    x_url = first_non_empty(item, ["x_url"])
    instagram_url = first_non_empty(item, ["instagram_url"])
    portfolio_url = first_non_empty(item, ["portfolio_url"])
    behance_url = first_non_empty(item, ["behance_url"])

    # Skills & software from enriched data
    skills_raw = item.get("skills") or []
    skills = []
    for s in skills_raw:
        if isinstance(s, str):
            skills.append(s)
        elif isinstance(s, dict) and s.get("name"):
            skills.append(s["name"])

    software_raw = item.get("software_items") or item.get("software") or []
    software = []
    for s in software_raw:
        if isinstance(s, str):
            software.append(s)
        elif isinstance(s, dict) and s.get("name"):
            software.append(s["name"])

    # Work samples from top_works
    top_works = item.get("top_works") or []
    work_samples = []
    for tw_url in top_works[:5]:
        work_samples.append(WorkSample(url=tw_url))

    return Candidate(
        full_name=full_name,
        title=job_title,
        bio=description,
        location=location,
        email=email,
        artstation_url=artstation_url,
        linkedin_url=linkedin_url,
        x_url=x_url,
        instagram_url=instagram_url,
        portfolio_url=portfolio_url,
        behance_url=behance_url,
        skills=skills,
        software=software,
        top_works=top_works,
        work_samples=work_samples,
        followers_count=_safe_int(item.get("followers_count")),
        experience_summary=description,
        source_platform=platform,
        source_url=source_url,
        raw=item,
    )


def _normalize_artstation_enriched(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize enriched ArtStation data (profile + projects structure)."""
    profile = item.get("profile") or item
    projects = item.get("projects") or []

    full_name = profile.get("full_name") or profile.get("username")
    headline = profile.get("headline") or profile.get("bio") or ""
    location_parts = [profile.get("city"), profile.get("country")]
    location = ", ".join(p for p in location_parts if p)

    # Social links
    social_profiles = profile.get("social_profiles") or []
    linkedin_url = None
    x_url = None
    portfolio_url = None
    behance_url = None

    for sp in social_profiles:
        sp_url = sp.get("url", "")
        platform_name = (sp.get("platform") or sp.get("network") or "").lower()
        if "linkedin" in platform_name or "linkedin.com" in sp_url:
            linkedin_url = sp_url
        elif "twitter" in platform_name or "x.com" in sp_url or "twitter.com" in sp_url:
            x_url = sp_url
        elif "behance" in platform_name or "behance.net" in sp_url:
            behance_url = sp_url
        elif sp_url and not portfolio_url:
            portfolio_url = sp_url

    if not portfolio_url:
        portfolio_url = profile.get("website") or profile.get("portfolio_url")

    # Skills & software
    skills_raw = profile.get("skills") or []
    skills = []
    for s in skills_raw:
        if isinstance(s, str):
            skills.append(s)
        elif isinstance(s, dict) and s.get("name"):
            skills.append(s["name"])

    software_raw = profile.get("software_items") or []
    software = []
    for s in software_raw:
        if isinstance(s, str):
            software.append(s)
        elif isinstance(s, dict) and s.get("name"):
            software.append(s["name"])

    # Top works / work samples
    work_samples: list[WorkSample] = []
    top_works: list[str] = []

    for proj in projects[:5]:
        proj_url = proj.get("permalink") or proj.get("url")
        if isinstance(proj_url, str):
            top_works.append(proj_url)

        cover = proj.get("cover") or {}
        thumbnail = cover.get("medium_image_url") or cover.get("small_image_url") or cover.get("thumb_url")

        work_samples.append(
            WorkSample(
                title=proj.get("title"),
                url=proj_url,
                thumbnail_url=thumbnail,
                description=proj.get("description"),
                likes_count=_safe_int(proj.get("likes_count")),
                views_count=_safe_int(proj.get("views_count")),
            )
        )

    username = profile.get("username", "")
    source_url = profile.get("permalink") or (f"https://www.artstation.com/{username}" if username else None)

    return Candidate(
        full_name=full_name,
        title=headline,
        bio=profile.get("bio"),
        location=location or None,
        email=profile.get("public_email"),
        linkedin_url=linkedin_url,
        x_url=x_url,
        portfolio_url=portfolio_url,
        artstation_url=source_url,
        behance_url=behance_url,
        top_works=top_works,
        work_samples=work_samples,
        skills=skills,
        software=software,
        followers_count=_safe_int(profile.get("followers_count")),
        experience_summary=headline,
        years_exp_estimate=_estimate_years_exp(profile),
        source_platform=platform,
        source_url=source_url,
        raw=item,
    )


# ── LinkedIn ─────────────────────────────────────────────────────────────


def _normalize_linkedin(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize LinkedIn result from harvestapi/linkedin-profile-search.

    Actual raw fields from the actor:
      firstName, lastName, headline, linkedinUrl,
      location: {linkedinText, countryCode, parsed: {text, ...}},
      currentPosition: [{companyName, position, ...}],
      experience: [{position, companyName, ...}],
      education: [{schoolName, degree, ...}],
      skills: [{name: ...}],
      about, followerCount, photo, etc.
    """
    # ── Name
    first = item.get("firstName", "")
    last = item.get("lastName", "")
    full_name = f"{first} {last}".strip() if (first or last) else None
    if not full_name:
        full_name = first_non_empty(item, ["fullName", "full_name", "name"])

    headline = first_non_empty(item, ["headline", "title", "position"])

    # ── Location (can be a dict or string)
    location_raw = item.get("location")
    location = None
    if isinstance(location_raw, dict):
        location = location_raw.get("linkedinText") or (location_raw.get("parsed", {}).get("text"))
    elif isinstance(location_raw, str):
        location = location_raw

    profile_url = first_non_empty(item, ["linkedinUrl", "profileUrl", "profile_url", "url"])

    # ── Current position
    current_positions = item.get("currentPosition") or []
    current_company_name = None
    if current_positions and isinstance(current_positions, list):
        first_pos = current_positions[0] if current_positions else {}
        current_company_name = first_pos.get("companyName")

    # ── Experience → previous companies
    experiences = item.get("experience") or item.get("experiences") or item.get("positions") or []
    previous_companies: list[str] = []
    for exp in experiences:
        if isinstance(exp, dict):
            company = exp.get("companyName") or exp.get("company")
            if isinstance(company, str) and company.strip() and company.strip() != current_company_name:
                if company.strip() not in previous_companies:
                    previous_companies.append(company.strip())

    # ── Skills
    skills_raw = item.get("skills") or item.get("topSkills") or []
    skills: list[str] = []
    for s in skills_raw:
        if isinstance(s, str):
            skills.append(s)
        elif isinstance(s, dict):
            name = s.get("name") or s.get("skill")
            if name:
                skills.append(name)

    # ── Email
    email = first_non_empty(item, ["email", "emailAddress", "email_address"])

    # ── Education
    educations = item.get("education") or item.get("educations") or item.get("profileTopEducation") or []
    notable_projects: list[str] = []
    for edu in educations:
        if isinstance(edu, dict):
            school = edu.get("schoolName") or edu.get("name")
            degree = edu.get("degree") or edu.get("degreeName")
            if school:
                entry = school
                if degree:
                    entry = f"{degree} @ {school}"
                notable_projects.append(entry)

    # ── Cross-platform links (from about text, websites, etc.)
    about_text = first_non_empty(item, ["about", "summary", "bio"]) or ""
    li, x_url, ig, portfolio = _extract_links({"bio": about_text})

    # Check about text for artstation/behance links
    import re
    artstation_url = None
    behance_url = None
    if about_text:
        m = re.search(r"artstation\.com/([a-zA-Z0-9_.-]+)", about_text.lower())
        if m and m.group(1) not in ("artwork", "search"):
            artstation_url = f"https://www.artstation.com/{m.group(1)}"
        m = re.search(r"behance\.net/([a-zA-Z0-9_.-]+)", about_text.lower())
        if m:
            behance_url = f"https://www.behance.net/{m.group(1)}"

    # Also check websites field
    websites = item.get("websites") or item.get("website") or []
    if isinstance(websites, str):
        websites = [websites]
    for w in websites:
        url = w.get("url") if isinstance(w, dict) else w
        if isinstance(url, str):
            url_lower = url.lower()
            if "artstation" in url_lower and not artstation_url:
                artstation_url = url
            elif "behance" in url_lower and not behance_url:
                behance_url = url
            elif not portfolio:
                portfolio = url

    return Candidate(
        full_name=full_name,
        title=headline,
        bio=about_text or None,
        location=location,
        email=email,
        linkedin_url=profile_url,
        x_url=x_url,
        instagram_url=ig,
        artstation_url=artstation_url,
        behance_url=behance_url,
        portfolio_url=portfolio,
        current_company=current_company_name,
        previous_companies=previous_companies[:5],
        notable_projects=notable_projects[:3],
        skills=skills,
        experience_summary=headline,
        years_exp_estimate=_estimate_years_exp(item),
        followers_count=_safe_int(item.get("followerCount") or item.get("connectionsCount")),
        source_platform=platform,
        source_url=profile_url,
        raw=item,
    )


# ── Instagram ────────────────────────────────────────────────────────────


def _normalize_instagram(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize Instagram result.

    Handles two formats:
    1. Profile details: {fullName, username, biography, followersCount, latestPosts, ...}
    2. Post/hashtag result: {ownerUsername, ownerFullName, caption, displayUrl, likesCount, ...}
    """
    # Detect format: posts have ownerUsername, profiles have username + biography
    owner_username = item.get("ownerUsername")
    if owner_username and not item.get("biography"):
        return _normalize_instagram_post(item, platform)

    return _normalize_instagram_profile(item, platform)


def _normalize_instagram_post(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize a single Instagram post (from hashtag search)."""
    username = item.get("ownerUsername") or item.get("username") or ""
    full_name = item.get("ownerFullName") or username
    source_url = f"https://www.instagram.com/{username}" if username else None

    caption = item.get("caption") or ""
    post_url = item.get("url")

    work_samples = []
    top_works = []
    if post_url:
        top_works.append(post_url)
        work_samples.append(
            WorkSample(
                title=item.get("alt") or caption[:60],
                url=post_url,
                thumbnail_url=item.get("displayUrl"),
                description=caption[:200],
                likes_count=_safe_int(item.get("likesCount")),
                views_count=_safe_int(item.get("videoViewCount")),
            )
        )

    return Candidate(
        full_name=full_name,
        bio=caption[:200] if caption else None,
        instagram_url=source_url,
        top_works=top_works,
        work_samples=work_samples,
        followers_count=_safe_int(item.get("ownerFollowerCount")),
        source_platform=platform,
        source_url=source_url,
        raw=item,
    )


def _normalize_instagram_profile(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize an Instagram profile details result."""
    full_name = item.get("fullName") or item.get("full_name") or item.get("username")
    bio = item.get("biography") or item.get("bio") or ""

    username = item.get("username", "")
    source_url = item.get("url") or (f"https://www.instagram.com/{username}" if username else None)

    # External links → Portfolio
    external_urls = item.get("externalUrls") or []
    portfolio_url = None
    if isinstance(external_urls, list) and external_urls:
        for eu in external_urls:
            url = eu.get("url") if isinstance(eu, dict) else eu
            if isinstance(url, str):
                portfolio_url = url
                break
    if not portfolio_url:
        portfolio_url = item.get("externalUrl")

    # Latest posts as work samples
    latest_posts = item.get("latestPosts") or []
    work_samples: list[WorkSample] = []
    top_works: list[str] = []

    for post in latest_posts[:5]:
        post_url = post.get("url")
        if isinstance(post_url, str):
            top_works.append(post_url)

        work_samples.append(
            WorkSample(
                title=post.get("alt"),
                url=post_url,
                thumbnail_url=post.get("displayUrl"),
                description=(post.get("caption") or "")[:200],
                likes_count=_safe_int(post.get("likesCount")),
                views_count=_safe_int(post.get("videoViewCount")),
            )
        )

    return Candidate(
        full_name=full_name,
        title=item.get("businessCategoryName"),
        bio=bio,
        location=None,
        email=None,
        instagram_url=source_url,
        portfolio_url=portfolio_url,
        top_works=top_works,
        work_samples=work_samples,
        followers_count=_safe_int(item.get("followersCount")),
        source_platform=platform,
        source_url=source_url,
        raw=item,
    )


# ── Generic / fallback ───────────────────────────────────────────────────


def _extract_links(item: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    links = item.get("links") if isinstance(item.get("links"), dict) else {}

    linkedin = first_non_empty(item, ["linkedin_url", "linkedin", "linkedinUrl"]) or first_non_empty(links, ["linkedin"])
    x_url = first_non_empty(item, ["x_url", "twitter_url", "twitter", "xUrl"]) or first_non_empty(links, ["x", "twitter"])
    instagram = first_non_empty(item, ["instagram_url", "instagram", "instagramUrl"]) or first_non_empty(links, ["instagram"])
    portfolio = first_non_empty(item, ["portfolio_url", "website", "portfolio", "portfolioUrl"]) or first_non_empty(
        links, ["portfolio", "website"]
    )

    # Nếu chưa có, thử tìm trong bio hoặc description
    raw_text = str(item.get("bio") or item.get("description") or item.get("text") or "")
    # Twitter bio từ Playwright innerText thường chứa newline giữa "http://\n" và domain
    # Clean: nối lại "http://\nxyz.com" → "http://xyz.com"
    import re
    text = re.sub(r"(https?://)\s+", r"\1", raw_text).lower()
    if text:
        if not linkedin:
            m = re.search(r"linkedin\.com/in/([a-zA-Z0-9_-]+)", text)
            if m: linkedin = f"https://www.linkedin.com/in/{m.group(1)}"
        if not instagram:
            m = re.search(r"instagram\.com/([a-zA-Z0-9_.]+)", text)
            if m: instagram = f"https://www.instagram.com/{m.group(1)}"
        if not portfolio:
            # Tìm link bất kỳ không phải social
            m = re.search(r"https?://(?!t\.co|twitter\.com|x\.com|linkedin\.com|instagram\.com|facebook\.com|t\.me)([a-zA-Z0-9.-]+\.[a-z]{2,}/?[^\s]*)", text)
            if m: portfolio = m.group(0)

    return linkedin, x_url, instagram, portfolio


def _normalize_generic(item: dict[str, Any], platform: str) -> Candidate:
    """Fallback normalizer for unknown platforms."""
    linkedin, x_url, instagram, portfolio = _extract_links(item)

    top_works: list[str] = []
    raw_top_works = item.get("top_works") or item.get("projects") or item.get("works") or []
    if isinstance(raw_top_works, list):
        for work in raw_top_works[:5]:
            if isinstance(work, str):
                top_works.append(work)
            elif isinstance(work, dict):
                url = work.get("url") or work.get("link")
                if isinstance(url, str) and url.strip():
                    top_works.append(url.strip())

    source_url = first_non_empty(item, ["profile_url", "url", "link"])

    return Candidate(
        full_name=first_non_empty(item, ["full_name", "name", "fullName"]),
        title=first_non_empty(item, ["title", "position", "headline", "bio"]),
        location=first_non_empty(item, ["location", "city", "country"]),
        email=first_non_empty(item, ["email", "public_email", "contactEmail"]),
        linkedin_url=linkedin,
        x_url=x_url,
        instagram_url=instagram,
        portfolio_url=portfolio,
        top_works=top_works,
        experience_summary=first_non_empty(item, ["experience_summary", "experience", "about"]),
        years_exp_estimate=_estimate_years_exp(item),
        source_platform=platform,
        source_url=source_url,
        raw=item,
    )


# ── X / Twitter ──────────────────────────────────────────────────────────


def _normalize_x(item: dict[str, Any], platform: str) -> Candidate:
    """Normalize a Twitter/X result from the free twitter_scraper API.

    The format is typically: {"user": {"name", "screen_name", "description", ...}}
    """
    user_info = item.get("user") or {}

    full_name = user_info.get("name") or user_info.get("screen_name", "")
    username = user_info.get("screen_name", "")
    bio = user_info.get("description", "")
    location = user_info.get("location", "")
    followers = user_info.get("followers_count")

    x_url = item.get("url") or (f"https://x.com/{username}" if username else "")
    
    # Extract links from bio and external URL
    li, x, ig, port = _extract_links({"bio": bio, "url": user_info.get("url", "")})

    return Candidate(
        full_name=full_name,
        title=bio[:200] if bio else None,
        location=location,
        bio=bio[:500] if bio else None,
        x_url=x_url,
        source_url=x_url,
        source_platform=platform,
        followers_count=_safe_int(followers),
        linkedin_url=li,
        instagram_url=ig,
        portfolio_url=port or user_info.get("url"),
        raw=item,
    )


# ── Normalizer registry ─────────────────────────────────────────────────

_NORMALIZERS = {
    "artstation": _normalize_artstation,
    "linkedin": _normalize_linkedin,
    "instagram": _normalize_instagram,
    "x": _normalize_x,
}
