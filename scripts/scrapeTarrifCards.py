from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

import re
import requests

from smartmeter.config import DATA_DIR

OUTPUT_DIR = DATA_DIR / "tarrifs"

DUTCH_MONTHS = (
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
)

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8",
}

PG_CONSENT_CACHE: str = (
    '{"isValid":true,"purposeChoices":[{"purpose":"TCF_1","accepted":true},'
    '{"purpose":"MARKETING","accepted":true},{"purpose":"SOCIAL_MEDIA","accepted":true},'
    '{"purpose":"PERSONALISATION","accepted":true},{"purpose":"FUNCTIONAL","accepted":true},'
    '{"purpose":"FEATURE_1","accepted":true},{"purpose":"FEATURE_2","accepted":true},'
    '{"purpose":"FEATURE_3","accepted":true},{"purpose":"SPECIAL_FEATURE_1","accepted":true},'
    '{"purpose":"SPECIAL_PURPOSE_1","accepted":true},{"purpose":"SPECIAL_PURPOSE_2","accepted":true},'
    '{"purpose":"SPECIAL_PURPOSE_3","accepted":true},{"purpose":"TCF_2","accepted":true},'
    '{"purpose":"TCF_3","accepted":true},{"purpose":"TCF_4","accepted":true},'
    '{"purpose":"TCF_7","accepted":true},{"purpose":"TCF_8","accepted":true},'
    '{"purpose":"TCF_9","accepted":true},{"purpose":"TCF_10","accepted":true}],'
    '"vendorChoices":[{"vendorId":{"value":"550","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"516","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"898","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"981","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"2577","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"12","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"10","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"115","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"304","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"32","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"11","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"758","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"119","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"108","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"76","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"213","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"149","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"69","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"807","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"108","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"50","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"799","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"28","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"2677","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"98","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"328","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"1126","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"110","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"164","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"612","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"553","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"94","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"412","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"77","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"4831","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"238","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"128","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"2923","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"507","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"573","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"284","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"264","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"565","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"63","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"61","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"91","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"1029","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"2072","source":"ATP"},"accepted":true},'
    '{"vendorId":{"value":"361","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"597","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"160","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"227","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"133","source":"TCF"},"accepted":true},'
    '{"vendorId":{"value":"1097","source":"ATP"},"accepted":true}]}'
)

@dataclass
class ProductPattern:
    name: str
    pattern: re.Pattern

@dataclass
class ProviderConfig:
    slug: str
    file_prefix: str
    products: list = field(default_factory=list)

PROVIDERS = [
    ProviderConfig(
        slug="dats24",
        file_prefix="Dats24",
        products=[
            ProductPattern(
                "Elektriciteit",
                re.compile(
                    r"^\s*(?:dats\s*24\s*)?(?:elektriciteit|[eé]lectricit[eé])"
                    r"(?:\s+(?:groen|verte))?(?:\s+(?:variabel|variable))?\s*$",
                    re.IGNORECASE,
                ),
            ),
        ],
    ),
    ProviderConfig(
        slug="eneco",
        file_prefix="Eneco",
        products=[
            ProductPattern(
                "Zon_Wind_Flex",
                re.compile(r"^\s*(?:zon|sun)\s*&\s*(?:wind|vent)\s*flex\s*$", re.IGNORECASE),
            ),
        ],
    ),
    ProviderConfig(
        slug="octaplus",
        file_prefix="OctaPlus",
        products=[
            ProductPattern("Eco_Clear", re.compile(r"^\s*eco\s*clear\s*$", re.IGNORECASE)),
            ProductPattern("Fixed", re.compile(r"^\s*fixed\s*$", re.IGNORECASE)),
        ],
    ),
    ProviderConfig(
        slug="bolt",
        file_prefix="Bolt",
        products=[
            ProductPattern(
                "Variabel",
                re.compile(r"^\s*(?:elektriciteit|[eé]lectricit[eé])\s+variab(?:el|le)\s*$", re.IGNORECASE),
            ),
        ],
    ),
]

def iter_year_months(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> list:
    if not (1 <= start_month <= 12 and 1 <= end_month <= 12):
        raise ValueError("Months must be between 1 and 12.")
    months = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        months.append((year, month))
        month = month % 12 + 1
        if month == 1:
            year += 1
    return months

def build_archive_url(slug: str, year: int, month: int) -> str:
    return f"https://www.mijnenergie.be/energieleveranciers/{slug}/tariefkaart-{DUTCH_MONTHS[month - 1]}-{year}#tariffResults"

def save_target_file(
    target_url: str,
    cookies: dict,
    output_dir: Path,
    file_name: str,
    timeout: float = 30.0,
) -> Path | None:
    try:
        response = requests.get(
            target_url,
            headers=DOWNLOAD_HEADERS,
            cookies=cookies,
            timeout=timeout,
            allow_redirects=True,
        )
        response.raise_for_status()
        if not response.content or not response.content.startswith(b"%PDF"):
            return None
    except requests.RequestException:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{file_name}.pdf"
    out_path.write_bytes(response.content)
    return out_path

def dismiss_cookie_banner(page: Page) -> bool:
    consent_selectors = (
        "#didomi-notice-agree-button",
        "button:has-text('Akkoord en verder')",
        "button:has-text('Akkoord')",
        "button:has-text('Alles accepteren')",
        "button:has-text('Accepteren')",
        "button:has-text('Accept')",
    )
    scopes = [page, *page.frames]
    for scope in scopes:
        for selector in consent_selectors:
            button = scope.locator(selector).first
            try:
                if button.is_visible(timeout=1000):
                    button.click(timeout=2000)
                    page.wait_for_timeout(1000)
                    return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue
    return False

def handle_privacy_gate(page: Page, timeout_ms: int = 15000) -> bool:
    if "myprivacy.dpgmedia.be" not in page.url and "privacy gate" not in page.title().lower():
        return False
    consent_selectors = (
        "button:has-text('Akkoord en verder')",
        "button:has-text('Akkoord')",
        "button:has-text('Alles accepteren')",
        "button:has-text('Accepteren')",
        "button:has-text('Accept')",
        "input[type='submit']",
        "button[type='submit']",
    )
    for scope in [page, *page.frames]:
        for selector in consent_selectors:
            button = scope.locator(selector).first
            try:
                if button.is_visible(timeout=1500):
                    button.click(timeout=3000)
                    try:
                        page.wait_for_url("**/mijnenergie.be/**", timeout=timeout_ms)
                        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                    except PlaywrightTimeoutError:
                        page.wait_for_timeout(2000)
                    return "mijnenergie.be" in page.url
            except Exception:
                continue
    return False

def find_vlaanderen_matches(page: Page, patterns: list) -> list:
    anchors = page.evaluate("""() => {
        const results = [];
        const allHeadings = [...document.querySelectorAll('h2, h3, h4')];
        const vlaanderenHeading = allHeadings.find(h => /vlaanderen/i.test(h.textContent));
        if (!vlaanderenHeading) return results;
        let container = vlaanderenHeading.parentElement;
        while (container && container !== document.body) {
            if (container.querySelectorAll('a[href]').length > 0) break;
            container = container.parentElement;
        }
        if (!container) return results;
        const linksInContainer = [...container.querySelectorAll('a[href]')];
        for (const a of linksInContainer) {
            const afterHeading = vlaanderenHeading.compareDocumentPosition(a) & Node.DOCUMENT_POSITION_FOLLOWING;
            if (!afterHeading) continue;
            const text = a.textContent.replace(/\\s+/g, ' ').trim();
            const href = (a.getAttribute('href') || '').trim();
            if (text && href && /\\.pdf/i.test(href)) results.push([text, href]);
        }
        return results;
    }""")
    matches = []
    for text, href in anchors:
        for product in patterns:
            if product.pattern.match(text):
                matches.append((text, href, product.name))
                break
    return matches

def run_scraper(
    providers: list = PROVIDERS,
    start_year: int = 2023,
    start_month: int = 1,
    end_year: int = 2026,
    end_month: int = 11,
    output_dir: Path = OUTPUT_DIR,
) -> None:
    months = iter_year_months(start_year, start_month, end_year, end_month)
    done = 0
    skipped = 0
    failed = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=DOWNLOAD_HEADERS["User-Agent"],
            locale="nl-BE",
            timezone_id="Europe/Brussels",
            extra_http_headers={"Accept-Language": DOWNLOAD_HEADERS["Accept-Language"]},
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.mijnenergie.be/", wait_until="domcontentloaded", timeout=30_000)
        if "myprivacy.dpgmedia.be" in page.url:
            handle_privacy_gate(page)
        else:
            dismiss_cookie_banner(page)
        try:
            for provider in providers:
                for year, month in months:
                    url = build_archive_url(provider.slug, year, month)
                    try:
                        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        status = response.status if response else "?"
                    except PlaywrightTimeoutError:
                        failed += 1
                        continue
                    except Exception:
                        failed += 1
                        continue
                    if status not in (200, "200"):
                        skipped += 1
                        continue
                    try:
                        page.locator("a[href*='.pdf'], a[href*='tariefkaart'], a[href*='tarief']").first.wait_for(state="attached", timeout=10_000)
                    except PlaywrightTimeoutError:
                        skipped += 1
                        continue
                    try:
                        page.get_by_role("heading", name=re.compile("vlaanderen", re.I)).first.wait_for(state="attached", timeout=15_000)
                    except PlaywrightTimeoutError:
                        skipped += 1
                        continue
                    matches = find_vlaanderen_matches(page, provider.products)
                    if not matches:
                        skipped += 1
                        continue
                    cookies = {
                        cookie["name"]: cookie["value"]
                        for cookie in context.cookies()
                        if "name" in cookie and "value" in cookie
                    }
                    matched_this_month = set()
                    for _, href, product_name in matches:
                        if product_name in matched_this_month:
                            continue
                        matched_this_month.add(product_name)
                        target_url = urljoin(page.url, href)
                        file_name = f"{provider.file_prefix.upper()}_{product_name.upper()}_{year}{month:02d}"
                        saved = save_target_file(target_url, cookies, output_dir, file_name)
                        if saved:
                            done += 1
                        else:
                            failed += 1
        finally:
            browser.close()

def main() -> None:
    run_scraper()

if __name__ == "__main__":
    main()
