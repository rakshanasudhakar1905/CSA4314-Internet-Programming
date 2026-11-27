import os
import re
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

PLATFORMS = {
    "Amazon": {
        "domain": "amazon.in",
        "search": "https://www.amazon.in/s?k={}"
    },
    "Flipkart": {
        "domain": "flipkart.com",
        "search": "https://www.flipkart.com/search?q={}"
    },
    "Myntra": {
        "domain": "myntra.com",
        "search": "https://www.myntra.com/{}"
    },
    "Meesho": {
        "domain": "meesho.com",
        "search": "https://www.meesho.com/search?q={}"
    },
    "Ajio": {
        "domain": "ajio.com",
        "search": "https://www.ajio.com/search/?text={}"
    }
}


def clean_price(price_str):
    if price_str is None:
        return None
    cleaned = re.sub(r"[^0-9.]", "", str(price_str))
    try:
        val = float(cleaned)
        return round(val, 2) if val > 0 else None
    except ValueError:
        return None


def simplify_query(query):
    core = re.sub(r"\([^)]*\)", "", query).strip()
    core = re.sub(r"\s+", " ", core)
    return core if len(core) >= 4 else query.strip()


def match_score(query, candidate_title):
    q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
    t_tokens = set(re.findall(r"[a-z0-9]+", candidate_title.lower()))
    if not q_tokens:
        return 0.0
    return len(q_tokens & t_tokens) / len(q_tokens)


def get_store_search_url(platform, query):
    encoded = urllib.parse.quote_plus(query)
    if platform == "Myntra":
        slug = re.sub(r"[^a-z0-9]+", "-", query.strip().lower()).strip("-")
        return f"https://www.myntra.com/{slug}" if slug else f"https://www.myntra.com/{encoded}"
    return PLATFORMS[platform]["search"].format(encoded)


def extract_direct_store_url(platform, *candidate_urls):
    """Return a clean URL belonging strictly to the target store, never Google/SerpApi."""
    target_domain = PLATFORMS[platform]["domain"]

    for raw_url in candidate_urls:
        if not raw_url or not isinstance(raw_url, str):
            continue

        url = raw_url.strip()

        # Unwrap Google redirect URLs like https://www.google.com/url?q=https://www.amazon.in/...
        parsed = urllib.parse.urlparse(url)
        if "google." in parsed.netloc.lower():
            qs = urllib.parse.parse_qs(parsed.query)
            for key in ("q", "url", "u"):
                if key in qs and qs[key]:
                    url = urllib.parse.unquote(qs[key][0])
                    parsed = urllib.parse.urlparse(url)
                    break

        host = parsed.netloc.lower()
        if target_domain in host and "google." not in host and "serpapi.com" not in host:
            return url

    return None


def detect_platform(text):
    t = text.lower()
    for name, cfg in PLATFORMS.items():
        if name.lower() in t or cfg["domain"] in t:
            return name
    return None


def fetch_google_shopping(query, api_key):
    results = {}
    params = {
        "engine": "google_shopping",
        "q": query,
        "gl": "in",
        "hl": "en",
        "num": 30,
        "api_key": api_key
    }
    try:
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=15)
        data = resp.json()
        for item in data.get("shopping_results", []):
            source = f"{item.get('source', '')} {item.get('link', '')} {item.get('product_link', '')}"
            platform = detect_platform(source)
            price = item.get("extracted_price") or clean_price(item.get("price"))
            if not platform or not price:
                continue

            direct_url = extract_direct_store_url(
                platform,
                item.get("link"),
                item.get("product_link")
            )
            if not direct_url:
                continue

            title = item.get("title", query)
            score = match_score(query, title)
            if platform not in results or score > results[platform]["_score"]:
                results[platform] = {
                    "platform": platform,
                    "title": title,
                    "price": float(price),
                    "url": direct_url,
                    "image": item.get("thumbnail", ""),
                    "_score": score
                }
    except Exception as e:
        print(f"[SerpApi Shopping Error]: {e}")
    return results


def fetch_store_via_google_organic(platform, core_query, full_query, api_key):
    domain = PLATFORMS[platform]["domain"]
    params = {
        "engine": "google",
        "q": f"site:{domain} {core_query}",
        "gl": "in",
        "hl": "en",
        "num": 5,
        "api_key": api_key
    }
    try:
        resp = requests.get("https://serpapi.com/search.json", params=params, timeout=12)
        data = resp.json()
        for item in data.get("organic_results", []):
            direct_url = extract_direct_store_url(platform, item.get("link"))
            if not direct_url:
                continue

            title = item.get("title", full_query)
            snippet = item.get("snippet", "")
            rich = item.get("rich_snippet", {})

            price = None
            if isinstance(rich, dict):
                top = rich.get("top", {}).get("detected_extensions", {})
                bottom = rich.get("bottom", {}).get("detected_extensions", {})
                price = top.get("price") or bottom.get("price")

            if not price:
                m = re.search(r"(?:₹|Rs\.?)\s*([0-9,]+(?:\.[0-9]{1,2})?)", f"{title} {snippet}")
                if m:
                    price = clean_price(m.group(1))

            if price:
                return {
                    "platform": platform,
                    "title": title,
                    "price": float(price),
                    "url": direct_url,
                    "image": item.get("thumbnail", "")
                }
    except Exception as e:
        print(f"[Organic Fallback Error - {platform}]: {e}")
    return None


def get_live_prices(query):
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    core_query = simplify_query(query)
    found = {}

    if api_key:
        found = fetch_google_shopping(query, api_key)
        if len(found) < 3 and core_query.lower() != query.lower():
            extra = fetch_google_shopping(core_query, api_key)
            for k, v in extra.items():
                if k not in found:
                    found[k] = v

        for platform in PLATFORMS:
            if platform not in found:
                organic_item = fetch_store_via_google_organic(platform, core_query, query, api_key)
                if organic_item:
                    found[platform] = organic_item

    platforms_data = {}
    for platform in PLATFORMS:
        if platform in found:
            item = found[platform]
            item.pop("_score", None)
            platforms_data[platform.lower()] = item
        else:
            platforms_data[platform.lower()] = {
                "platform": platform,
                "title": f"{core_query} (Check directly on {platform})",
                "price": None,
                "url": get_store_search_url(platform, core_query),
                "image": ""
            }

    priced_items = [v for v in platforms_data.values() if v["price"] is not None]
    recommendation = None

    if priced_items:
        priced_items.sort(key=lambda x: x["price"])
        best = priced_items[0]
        second_price = priced_items[1]["price"] if len(priced_items) > 1 else best["price"]
        recommendation = {
            "best_platform": best["platform"],
            "lowest_price": best["price"],
            "savings": max(0, round(second_price - best["price"], 2)),
            "buy_url": best["url"]
        }

    return {
        "query": query,
        "platforms": platforms_data,
        "recommendation": recommendation
    }