import requests
import os
import json
from datetime import datetime
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuration ---
API_KEYS = [
    "df9ebfee868506bcf0ff042b76582dc6",
    "7d6edd0f8f6a9599fd5d8528b495532c",
    "f99c07ccbc39bd2ddda0622c03b4d705",
    "ee80ac20239ca7ac2308d759b3351e8f",
    "5d21f0e5a6c1723bbc24dc4d8a4bc05f",
    "040887ef4b6cb5fb849cf83fbd7e6033",
]

SCRAPERAPI_ACCOUNT_URL = "https://api.scraperapi.com/account"

CHITTORGARH_API_ENDPOINTS = {
    "current": "https://webnodejs.chittorgarh.com/cloud/report/data-read/82/1/5/{current_year}/2025-26/0/all/0?search=&v=16-19",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Connection': 'keep-alive',
    'Referer': 'https://www.chittorgarh.com/',
}

OUTPUT_DIR = "IPO_DATA"


def get_current_year():
    return datetime.now().year


def get_available_scraperapi_key():
    for key in API_KEYS:
        try:
            res = requests.get(f"{SCRAPERAPI_ACCOUNT_URL}?api_key={key}", timeout=10)
            data = res.json()
            if data.get("requestCount", 1001) < data.get("requestLimit", 1000):
                return key
        except:
            continue
    return None


def scrape_json_data(url, api_key):
    try:
        full_url = f"http://api.scraperapi.com/?api_key={api_key}&url={url}"
        res = requests.get(full_url, headers=HEADERS, timeout=30)
        return res.json()
    except:
        return None


def scrape_data_with_scraperapi(url, api_key):
    try:
        full_url = f"http://api.scraperapi.com/?api_key={api_key}&url={url}"
        return requests.get(full_url, headers=HEADERS, timeout=30)
    except:
        return None


def extract_ipo_info(report_data):
    ipo_info_list = []
    for item in report_data:
        company_html = item.get("Company", "")
        ipo_name = item.get("~compare_name", "").strip()

        ipo_url = None
        if 'href="' in company_html:
            start = company_html.find('href="') + 6
            end = company_html.find('"', start)
            ipo_url = company_html[start:end]

        if ipo_name and ipo_url:
            ipo_info_list.append({
                "name": ipo_name,
                "url": ipo_url
            })
    return ipo_info_list


def get_html_path(ipo_name, year):
    safe_name = "".join(c if c.isalnum() or c in (' ', '_', '-') else "_" for c in ipo_name).strip()
    filename = f"{safe_name}.html"
    html_dir = os.path.join(OUTPUT_DIR, str(year), "html")
    os.makedirs(html_dir, exist_ok=True)
    return os.path.join(html_dir, filename)


def fetch_and_save_ipo_html(ipo, year, api_key, force_fetch=False):
    ipo_name = ipo["name"]
    ipo_url = ipo["url"]

    if ipo_url.startswith("/"):
        ipo_url = urljoin("https://www.chittorgarh.com", ipo_url)

    file_path = get_html_path(ipo_name, year)

    if not force_fetch and os.path.isfile(file_path):
        print(f"[SKIP] Already exists: {ipo_name}")
        return ipo, os.path.relpath(file_path, OUTPUT_DIR)

    print(f"[FETCH] {'Re-fetching' if force_fetch else 'Fetching'}: {ipo_name}")
    res = scrape_data_with_scraperapi(ipo_url, api_key)
    if res and res.status_code == 200:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(res.text)
            print(f"[SAVED] {ipo_name}")
            return ipo, os.path.relpath(file_path, OUTPUT_DIR)
        except:
            print(f"[ERROR] Failed to save: {ipo_name}")
    else:
        print(f"[ERROR] Failed to fetch: {ipo_name}")
    return ipo, None


def save_meta_data(meta, year, endpoint_name):
    year_dir = os.path.join(OUTPUT_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)
    file_path = os.path.join(year_dir, f"{endpoint_name}_meta.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"[META] Saved meta to {file_path}")


def main(year=None, endpoints_to_scrape=None):
    if year is None:
        year = get_current_year()

    if endpoints_to_scrape is None:
        endpoints_to_scrape = CHITTORGARH_API_ENDPOINTS.keys()

    api_key = get_available_scraperapi_key()
    if not api_key:
        print("❌ No available ScraperAPI key.")
        return

    for endpoint_name in endpoints_to_scrape:
        print(f"\n--- {endpoint_name.upper()} ---")
        api_url = CHITTORGARH_API_ENDPOINTS[endpoint_name].format(current_year=year)
        raw = scrape_json_data(api_url, api_key)
        report_data = raw.get("reportTableData", []) if raw else []
        ipo_list = extract_ipo_info(report_data)

        if not ipo_list:
            print("No IPO data found.")
            continue

        # First 5 IPOs: always re-fetch
        top5 = ipo_list[:5]
        remaining = ipo_list[5:]

        final_meta = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []

            for ipo in top5:
                futures.append(executor.submit(fetch_and_save_ipo_html, ipo, year, api_key, True))

            for ipo in remaining:
                file_path = get_html_path(ipo["name"], year)
                if os.path.isfile(file_path):
                    print(f"[SKIP] {ipo['name']} (already downloaded)")
                    ipo["html_path"] = os.path.relpath(file_path, OUTPUT_DIR)
                    final_meta.append(ipo)
                else:
                    futures.append(executor.submit(fetch_and_save_ipo_html, ipo, year, api_key, False))

            for f in as_completed(futures):
                ipo, html_path = f.result()
                ipo["html_path"] = html_path
                ipo["year"] = get_current_year()
                final_meta.append(ipo)

        save_meta_data(final_meta, year, endpoint_name)


if __name__ == "__main__":
    main()
