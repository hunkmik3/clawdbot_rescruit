import os
import logging
import urllib.parse
from typing import Any
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


def _create_browser_context(p):
    """Tạo browser context dùng chung cho tất cả các hàm scrape."""
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
    ct0 = os.getenv("TWITTER_CT0", "").strip()

    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800}
    )
    context.add_cookies([
        {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
        {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"}
    ])
    return browser, context


def _extract_users_from_page(page, selector_scope="document") -> list[dict]:
    """Trích xuất danh sách user từ UserCell trên trang hiện tại."""
    js_code = """(scope) => {
        const results = [];
        const root = scope === 'primaryColumn'
            ? document.querySelector('[data-testid="primaryColumn"]')
            : document;
        if (!root) return [];

        const cells = root.querySelectorAll('[data-testid="UserCell"]');

        cells.forEach(cell => {
            const bioEl = cell.querySelector('[data-testid="userDescription"]');
            const cellText = cell.innerText || "";
            const lines = cellText.split('\\n');

            const handleLine = lines.find(l => l.startsWith('@'));
            const handle = handleLine ? handleLine.replace('@', '') : "";
            const name = lines[0];
            const bio = bioEl ? bioEl.innerText : "";

            if (handle) {
                results.push({
                    name: name || handle,
                    screen_name: handle,
                    description: bio
                });
            }
        });
        return results;
    }"""
    return page.evaluate(js_code, selector_scope)


def _enrich_user_profile(context, screen_name: str) -> dict:
    """Mở tab MỚI, vào profile của user để lấy location thật + followers + bio.

    Dùng context (không phải page) để tạo tab riêng, tránh xung đột navigation.
    """
    profile_url = f"https://x.com/{screen_name}"
    result = {"location": "", "followers_count": None, "description": ""}

    profile_page = None
    try:
        profile_page = context.new_page()
        profile_page.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
        profile_page.wait_for_timeout(3000)

        # Trích xuất location + followers + bio từ profile page
        profile_data = profile_page.evaluate("""() => {
            const data = { location: "", followers_count: null, description: "" };

            // === BIO / DESCRIPTION ===
            const bioEl = document.querySelector('[data-testid="UserDescription"]');
            if (bioEl) {
                data.description = (bioEl.innerText || bioEl.textContent || "").trim();
            }

            // === LOCATION ===
            // Twitter profile header chứa: location, website, joined date
            // Mỗi item nằm trong một child element riêng biệt bên trong UserProfileHeader_Items
            const headerItems = document.querySelector('[data-testid="UserProfileHeader_Items"]');
            if (headerItems) {
                // Lấy từng child element trực tiếp (mỗi cái là 1 metadata item)
                const children = headerItems.children;
                for (const child of children) {
                    const text = (child.innerText || "").trim();
                    if (!text) continue;

                    // Bỏ qua nếu chứa "Joined" (ngày tham gia)
                    if (text.includes('Joined')) continue;
                    // Bỏ qua nếu chứa "Born" (ngày sinh)
                    if (text.includes('Born')) continue;
                    // Bỏ qua nếu là URL (website)
                    if (text.includes('.com') || text.includes('.org') || text.includes('.net')
                        || text.includes('http') || text.includes('.io') || text.includes('.co/')) continue;
                    // Bỏ qua nếu quá dài (không phải location)
                    if (text.length > 80) continue;
                    // Bỏ qua nếu quá ngắn
                    if (text.length < 2) continue;

                    // Nếu qua được tất cả filter → đây là location
                    data.location = text;
                    break;
                }
            }

            // === FOLLOWERS ===
            // Thử nhiều selector vì Twitter hay thay đổi layout
            const followersSelectors = [
                'a[href$="/verified_followers"]',
                'a[href$="/followers"]',
                'a[href*="/followers"]'
            ];
            for (const sel of followersSelectors) {
                const followersLink = document.querySelector(sel);
                if (followersLink) {
                    const countText = (followersLink.innerText || followersLink.textContent || "").trim();
                    // Match số với suffix K/M/B (ví dụ: "1.5K", "23M", "456")
                    const match = countText.match(/([\d,.]+)\s*([KMBkmb])?/);
                    if (match) {
                        let num = parseFloat(match[1].replace(/,/g, ''));
                        const suffix = (match[2] || "").toUpperCase();
                        if (suffix === 'K') num = num * 1000;
                        else if (suffix === 'M') num = num * 1000000;
                        else if (suffix === 'B') num = num * 1000000000;
                        if (!isNaN(num) && num > 0) {
                            data.followers_count = Math.round(num);
                            break;
                        }
                    }
                }
            }
            // Fallback: tìm số followers từ aria-label hoặc title
            if (data.followers_count === null) {
                const allLinks = document.querySelectorAll('a[href*="followers"]');
                for (const link of allLinks) {
                    const ariaLabel = link.getAttribute('aria-label') || "";
                    const match = ariaLabel.match(/([\d,]+)\s*[Ff]ollower/);
                    if (match) {
                        data.followers_count = parseInt(match[1].replace(/,/g, ''));
                        break;
                    }
                }
            }

            return data;
        }""")

        result = profile_data or result

    except Exception as e:
        logger.debug(f"[Twitter] Could not enrich @{screen_name}: {e}")
    finally:
        if profile_page:
            try:
                profile_page.close()
            except Exception:
                pass

    return result


def scrape_twitter(keywords: list[str], location: str = "", max_items: int = 15) -> list[dict[str, Any]]:
    """Twitter Scraper with profile enrichment for real location data."""
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
    ct0 = os.getenv("TWITTER_CT0", "").strip()

    if not auth_token or not ct0:
        logger.warning("[Twitter] Missing cookies.")
        raise ValueError("Missing TWITTER_AUTH_TOKEN or TWITTER_CT0")

    # Xây dựng query tìm kiếm
    query = " ".join(keywords)
    if location:
        query = f"{query} {location}"

    url = f"https://x.com/search?q={urllib.parse.quote(query)}&f=user"
    logger.info(f"[Twitter] TRUY CẬP: {url}")

    candidates = []

    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        try:
            # Bước 1: Tìm kiếm People
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

            try:
                page.wait_for_selector('[data-testid="primaryColumn"]', timeout=15000)
                logger.info("[Twitter] Đã thấy cột kết quả chính.")
            except:
                pass

            page.wait_for_timeout(5000)

            # Trích xuất danh sách user từ cột chính
            users_data = _extract_users_from_page(page, "primaryColumn")
            logger.info(f"[Twitter] Tìm thấy {len(users_data)} user từ search.")

            # Bước 2: Enrich — Vào từng profile để lấy location thật + followers + bio
            for u in users_data[:max_items]:
                screen_name = u['screen_name']
                logger.info(f"[Twitter] Enriching @{screen_name}...")

                profile_info = _enrich_user_profile(context, screen_name)
                real_location = profile_info.get("location", "")
                followers = profile_info.get("followers_count")
                # Ưu tiên bio từ profile page (đầy đủ hơn), fallback về bio từ search
                real_bio = profile_info.get("description") or u.get("description", "")

                candidates.append({
                    "user": {
                        "name": u['name'],
                        "screen_name": screen_name,
                        "description": real_bio,
                        "location": real_location or location,
                        "followers_count": followers
                    },
                    "url": f"https://x.com/{screen_name}"
                })

        except Exception as e:
            logger.error(f"[Twitter] Lỗi: {e}")
        finally:
            browser.close()

    # Bước 3: Post-filter — Nếu user nhập location, lọc lại kết quả
    if location:
        location_lower = location.lower()
        filtered = []
        for c in candidates:
            user_loc = (c["user"].get("location") or "").lower()
            user_bio = (c["user"].get("description") or "").lower()
            user_name = (c["user"].get("name") or "").lower()
            # Giữ lại nếu location/bio/name chứa từ khóa vị trí
            if (location_lower in user_loc
                or location_lower in user_bio
                or location_lower in user_name):
                filtered.append(c)
            else:
                logger.debug(f"[Twitter] Loại bỏ @{c['user']['screen_name']} (location: {user_loc}) - không khớp '{location}'")

        if filtered:
            candidates = filtered
        # Nếu filter ra 0 kết quả, giữ nguyên danh sách gốc để user tự đánh giá

    return candidates[:max_items]


def scrape_twitter_connections(screen_name: str, connection_type: str = "followers", max_items: int = 20) -> list[dict[str, Any]]:
    """Scrape followers or following of a specific user, with real location enrichment.
    
    Handles Twitter's new UI:
    - /followers now defaults to "Verified Followers" tab
    - Need to click on "Followers" tab explicitly
    - /following works normally
    """
    auth_token = os.getenv("TWITTER_AUTH_TOKEN", "").strip()
    ct0 = os.getenv("TWITTER_CT0", "").strip()

    if not auth_token or not ct0:
        raise ValueError("Missing TWITTER_AUTH_TOKEN or TWITTER_CT0")

    url = f"https://x.com/{screen_name}/{connection_type}"
    logger.info(f"[Twitter] DEEP SCAN ({connection_type}): {url}")

    candidates = []

    with sync_playwright() as p:
        browser, context = _create_browser_context(p)
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            # Twitter mặc định hiển thị "Verified Followers" khi vào /followers
            # Cần click vào tab "Followers" thực sự
            if connection_type == "followers":
                try:
                    # Tìm và click tab "Followers" (không phải "Verified Followers")
                    tabs = page.query_selector_all('nav[role="navigation"] a, [role="tablist"] a, [role="tab"]')
                    for tab in tabs:
                        tab_text = (tab.inner_text() or "").strip()
                        # Click tab "Followers" chính xác (không phải "Verified Followers")
                        if tab_text == "Followers":
                            logger.info(f"[Twitter] Clicking 'Followers' tab...")
                            tab.click()
                            page.wait_for_timeout(3000)
                            break
                except Exception as tab_err:
                    logger.warning(f"[Twitter] Could not click Followers tab: {tab_err}")

            # Đợi UserCell xuất hiện
            try:
                page.wait_for_selector('[data-testid="UserCell"]', timeout=15000)
                logger.info(f"[Twitter] UserCells loaded.")
            except:
                logger.warning(f"[Twitter] No UserCells found after waiting.")

            page.wait_for_timeout(3000)

            # Cuộn nhiều lần để lấy thêm kết quả
            scroll_rounds = max(1, (max_items + 9) // 10)
            for i in range(scroll_rounds):
                page.evaluate("window.scrollBy(0, 1200)")
                page.wait_for_timeout(2000)

            users_data = _extract_users_from_page(page, "document")
            logger.info(f"[Twitter] Tìm thấy {len(users_data)} connections.")

            # Enrich từng profile để lấy location thật + followers + bio
            for u in users_data[:max_items]:
                sn = u['screen_name']
                logger.info(f"[Twitter] Enriching connection @{sn}...")

                profile_info = _enrich_user_profile(context, sn)
                real_location = profile_info.get("location", "")
                followers = profile_info.get("followers_count")
                real_bio = profile_info.get("description") or u.get("description", "")

                candidates.append({
                    "user": {
                        "name": u['name'],
                        "screen_name": sn,
                        "description": real_bio,
                        "location": real_location or "",
                        "followers_count": followers
                    },
                    "url": f"https://x.com/{sn}"
                })

        except Exception as e:
            logger.error(f"[Twitter] Deep scan failed: {e}")
        finally:
            browser.close()

    return candidates[:max_items]
