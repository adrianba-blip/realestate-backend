import time
import re
from typing import List, Dict

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# CONFIG
# -----------------------------

CACHE_TTL_SECONDS = 60 * 60  # 1 hour cache
_cache: Dict[str, Dict] = {}

BUILDINGS = [
    "McKinley Hill Garden Villas",
    "Viceroy Towers",
    "Tuscany Residences at McKinley",
    "Uptown Parksuites",
]

# -----------------------------
# FUZZY MATCHING
# -----------------------------

def normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def fuzzy_match(building: str, text: str) -> bool:
    if not text:
        return False

    b = normalize_text(building)
    t = normalize_text(text)

    if b in t or t in b:
        return True

    if len(b) < 5 or len(t) < 5:
        return False

    mismatches = sum(1 for x, y in zip(b, t) if x != y)
    allowed = max(2, len(b) // 4)

    return mismatches <= allowed

def matches_any_building(text: str) -> bool:
    return any(fuzzy_match(b, text) for b in BUILDINGS)

# -----------------------------
# CACHE
# -----------------------------

def cache_key(building: str, max_budget: int, bedrooms: int) -> str:
    return f"{building}|{max_budget}|{bedrooms}"

def get_from_cache(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > CACHE_TTL_SECONDS:
        return None
    return entry["data"]

def set_cache(key: str, data):
    _cache[key] = {"timestamp": time.time(), "data": data}

# -----------------------------
# NORMALIZER
# -----------------------------

def normalize_listing(source, title, price, date, detail_url, search_url):
    return {
        "source": source,
        "title": title.strip(),
        "price": price.strip(),
        "date": date.strip(),
        "detail_url": detail_url,
        "search_url": search_url,
    }

# -----------------------------
# SCRAPERS
# -----------------------------

def scrape_rentpad(building, max_budget, bedrooms):
    results = []
    base_url = "https://rentpad.com.ph/for-rent/taguig"
    params = {"q": building}

    try:
        resp = requests.get(base_url, params=params, timeout=15)
        search_url = resp.url

        if resp.status_code != 200:
            return [normalize_listing("Rentpad", f"Search for {building}", "", "", search_url, search_url)]

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".listing-card, .property-card, .col-md-4")

        if not cards:
            return [normalize_listing("Rentpad", f"Search for {building}", "", "", search_url, search_url)]

        for card in cards[:20]:
            title_el = card.select_one("h2, h3, .title, .listing-title")
            price_el = card.select_one(".price, .listing-price")
            link_el = card.select_one("a")

            title = title_el.get_text(strip=True) if title_el else ""
            price = price_el.get_text(strip=True) if price_el else ""
            detail_url = link_el["href"] if link_el and link_el.has_attr("href") else search_url
            if detail_url.startswith("/"):
                detail_url = "https://rentpad.com.ph" + detail_url

            combined = f"{title} {price} {detail_url}"
            if not matches_any_building(combined):
                continue

            results.append(normalize_listing("Rentpad", title, price, "Rentpad", detail_url, search_url))

        return results

    except Exception:
        return [normalize_listing("Rentpad", f"Search for {building}", "", "", f"{base_url}?q={building}", f"{base_url}?q={building}")]


def scrape_lamudi(building, max_budget, bedrooms):
    results = []
    base_url = "https://www.lamudi.com.ph/taguig-city/"
    params = {"q": building}

    try:
        resp = requests.get(base_url, params=params, timeout=15)
        search_url = resp.url

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".ListingCell, .card, article")

        if not cards:
            return [normalize_listing("Lamudi", f"Search for {building}", "", "", search_url, search_url)]

        for card in cards[:20]:
            title_el = card.select_one("h2, h3, .ListingCell-KeyInfo-title")
            price_el = card.select_one(".ListingCell-KeyInfo-price, .price")
            link_el = card.select_one("a")

            title = title_el.get_text(strip=True) if title_el else ""
            price = price_el.get_text(strip=True) if price_el else ""
            detail_url = link_el["href"] if link_el and link_el.has_attr("href") else search_url
            if detail_url.startswith("/"):
                detail_url = "https://www.lamudi.com.ph" + detail_url

            combined = f"{title} {price} {detail_url}"
            if not matches_any_building(combined):
                continue

            results.append(normalize_listing("Lamudi", title, price, "Lamudi", detail_url, search_url))

        return results

    except Exception:
        return [normalize_listing("Lamudi", f"Search for {building}", "", "", f"{base_url}?q={building}", f"{base_url}?q={building}")]


def scrape_dotproperty(building, max_budget, bedrooms):
    search_url = f"https://www.dotproperty.com.ph/condos-for-rent/taguig?q={building}"
    return [normalize_listing("DotProperty", f"Search for {building}", "", "", search_url, search_url)]


def scrape_carousell(building, max_budget, bedrooms):
    search_url = f"https://www.carousell.ph/search/{building.replace(' ', '%20')}?condition=for-rent"
    return [normalize_listing("Carousell", f"Search for {building}", "", "", search_url, search_url)]


def scrape_myproperty(building, max_budget, bedrooms):
    search_url = f"https://www.myproperty.ph/rent/taguig?keyword={building.replace(' ', '%20')}"
    return [normalize_listing("MyProperty", f"Search for {building}", "", "", search_url, search_url)]


def run_all_scrapers(building, max_budget, bedrooms):
    results = []
    results.extend(scrape_rentpad(building, max_budget, bedrooms))
    results.extend(scrape_lamudi(building, max_budget, bedrooms))
    results.extend(scrape_dotproperty(building, max_budget, bedrooms))
    results.extend(scrape_carousell(building, max_budget, bedrooms))
    results.extend(scrape_myproperty(building, max_budget, bedrooms))
    return results

# -----------------------------
# ENDPOINT
# -----------------------------

@app.get("/search")
def search(building: str, max_budget: int, bedrooms: int):
    matched = None
    for b in BUILDINGS:
        if fuzzy_match(b, building):
            matched = b
            break

    if not matched:
        return {"results": [], "error": "Building not recognized (even fuzzy)."}

    key = cache_key(matched, max_budget, bedrooms)
    cached = get_from_cache(key)
    if cached:
        return {"results": cached, "cached": True}

    results = run_all_scrapers(matched, max_budget, bedrooms)
    set_cache(key, results)

    return {"results": results, "cached": False}
