import os
import json
from flask import Flask, jsonify, abort, request
from datetime import datetime, date
import re
import unicodedata
import logging
import threading
import time

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO) # Set Flask app logger level

# Base directory for IPO data
IPO_DATA_BASE_DIR = 'IPO_DATA'

# In-memory cache for IPO data
# Structure: {year: {'meta_mtime': float, 'meta_data': [], 'ipo_data': {json_path_identifier: {'mtime': float, 'data': {}}}}}
# 'meta_data' holds entries from current_meta.json (lightweight)
# 'ipo_data' holds full JSON content for individual IPOs, loaded lazily
ipo_cache = {}

# Cache refresh interval (in seconds, 4 hours = 4 * 60 * 60)
CACHE_REFRESH_INTERVAL_SECONDS = 4 * 60 * 60

def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    value = str(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('utf-8')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    value = re.sub(r'[-\s]+', '-', value)
    return value

def parse_date_robustly(date_string):
    """
    Attempts to parse a date string into a datetime object using multiple formats.
    Returns a date object.
    """
    formats = [
        '%b %d, %Y',             # May 14, 2025
        '%a, %b %d, %Y',         # Wed, May 14, 2025
        '%d %b %Y'               # 14 May 2025 (less common in your data but good to have)
    ]
    for fmt in formats:
        try:
            # Return date object, not datetime
            return datetime.strptime(date_string.strip(), fmt).date()
        except ValueError:
            continue
    return None


def get_ipo_status(ipo_details):
    """
    Determines the status of an IPO based on its IPO Date and Listing Date.
    Returns 'Upcoming', 'Open', 'Closed', or 'Unknown'.
    """
    ipo_date_range_str = None
    listing_date_str = None

    for detail in ipo_details:
        if detail[0] == "IPO Date":
            ipo_date_range_str = detail[1]
        elif detail[0] == "Listing Date":
            listing_date_str = detail[1]

    if not ipo_date_range_str:
        app.logger.debug("IPO Date not found in details for status calculation.")
        return "Unknown"

    ipo_open_date = None
    ipo_close_date = None

    # Try to parse date range like "May 14, 2025toMay 16, 2025"
    date_match = re.match(r'(\w+ \d+, \d{4})to(\w+ \d+, \d{4})', ipo_date_range_str)
    if date_match:
        ipo_open_date_str = date_match.group(1)
        ipo_close_date_str = date_match.group(2)
        ipo_open_date = parse_date_robustly(ipo_open_date_str)
        ipo_close_date = parse_date_robustly(ipo_close_date_str)
    else:
        # If no range, assume it's a single date for both open and close
        ipo_open_date = parse_date_robustly(ipo_date_range_str)
        ipo_close_date = ipo_open_date # For single date IPOs, open and close are the same

    if not ipo_open_date or not ipo_close_date:
        app.logger.debug(f"Failed to parse IPO dates from '{ipo_date_range_str}'.")
        return "Unknown"

    current_date_only = date.today() # Get today's date

    if current_date_only < ipo_open_date:
        return "Upcoming"
    elif ipo_open_date <= current_date_only <= ipo_close_date:
        return "Open"
    elif current_date_only > ipo_close_date:
        # If closed, also check listing date for a more precise "closed" status
        if listing_date_str:
            listing_date_match = re.search(r'(\w+ \d+, \d{4})', listing_date_str)
            if listing_date_match:
                listing_date = parse_date_robustly(listing_date_match.group(0))
                if listing_date and current_date_only >= listing_date:
                    return "Closed"
        return "Closed" # Default to closed if post IPO close date, even without listing
    else:
        app.logger.debug(f"Unhandled date comparison for IPO: Open={ipo_open_date}, Close={ipo_close_date}, Current={current_date_only}")
        return "Unknown"


def load_year_data(year):
    """
    Loads or reloads all IPO meta data for a given year into the cache.
    Checks modification times to ensure fresh data. This function only loads meta_data.
    """
    year_dir = os.path.join(IPO_DATA_BASE_DIR, str(year))
    meta_file = os.path.join(year_dir, 'current_meta.json')

    if not os.path.exists(year_dir):
        app.logger.warning(f"Year directory not found: {year_dir}")
        return False
    if not os.path.exists(meta_file):
        app.logger.warning(f"Meta file not found for year {year}: {meta_file}")
        return False

    current_meta_mtime = os.path.getmtime(meta_file)

    # Check if we need to reload meta data for this year
    if year not in ipo_cache or ipo_cache[year]['meta_mtime'] < current_meta_mtime:
        app.logger.info(f"Reloading meta data for year {year} from {meta_file}")
        try:
            with open(meta_file, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            # Add slug to meta_data for easier lookup
            for item in meta_data:
                if 'name' in item:
                    item['slug'] = slugify(item['name'])
            ipo_cache[year] = {
                'meta_mtime': current_meta_mtime,
                'meta_data': meta_data,
                'ipo_data': {}  # Crucially, individual IPO detail cache for this year is cleared/initialized empty
            }
            app.logger.info(f"Successfully loaded {len(meta_data)} IPOs for year {year} (meta only).")
        except json.JSONDecodeError as e:
            app.logger.error(f"Error decoding JSON from {meta_file}: {e}")
            return False
        except Exception as e:
            app.logger.error(f"Error loading meta data for {year} from {meta_file}: {e}")
            return False
    return True

def get_ipo_detail_data(year, ipo_json_path):
    """
    Retrieves individual IPO data from cache or loads it from file (lazy loading).
    Checks modification time for freshness.
    """
    # Assuming json_path already contains the year and json/ part, e.g., "2025/json/Astonea_Labs_Ltd_IPO.json"
    full_path = os.path.join(IPO_DATA_BASE_DIR, ipo_json_path)
    ipo_identifier = ipo_json_path # Using json_path as unique key in cache for details

    # Ensure the year's meta data structure exists in cache before accessing ipo_data sub-dict
    if year not in ipo_cache:
        # This shouldn't typically happen if load_year_data is called properly upstream,
        # but as a fallback, ensure year's meta is loaded.
        app.logger.debug(f"Attempting to load year data for {year} before getting IPO detail.")
        if not load_year_data(year):
            app.logger.error(f"Failed to load meta data for year {year}, cannot get detail data for {ipo_json_path}")
            return None

    if not os.path.exists(full_path):
        app.logger.error(f"IPO detail file not found: {full_path}")
        return None

    current_mtime = os.path.getmtime(full_path)

    # Check if we need to reload individual IPO data from disk
    if ipo_identifier not in ipo_cache[year]['ipo_data'] or \
       ipo_cache[year]['ipo_data'][ipo_identifier]['mtime'] < current_mtime:
        app.logger.info(f"Loading/Reloading detail data for {ipo_identifier} in year {year} from {full_path}")
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                ipo_data = json.load(f)
            ipo_cache[year]['ipo_data'][ipo_identifier] = {
                'mtime': current_mtime,
                'data': ipo_data
            }
            app.logger.info(f"Successfully loaded detail data for {ipo_identifier}.")
        except json.JSONDecodeError as e:
            app.logger.error(f"Error decoding JSON from {full_path}: {e}")
            return None
        except Exception as e:
            app.logger.error(f"Error loading IPO detail data from {full_path}: {e}")
            return None
    return ipo_cache[year]['ipo_data'][ipo_identifier]['data']

def get_nested_value(data, key_path):
    """
    Safely retrieves a nested value from a dictionary/list using a dot-separated key path.
    Returns None if any part of the path does not exist.
    Supports list indexing (e.g., 'ipo_details.0.1').
    """
    keys = key_path.split('.')
    current_value = data
    for key in keys:
        if isinstance(current_value, dict) and key in current_value:
            current_value = current_value[key]
        elif isinstance(current_value, list) and key.isdigit(): # Allow indexing into lists
            try:
                index = int(key)
                if 0 <= index < len(current_value):
                    current_value = current_value[index]
                else:
                    return None # Index out of bounds
            except ValueError:
                return None # Not a valid integer index
        else:
            return None # Key not found or type mismatch
    return current_value


@app.route('/api/ipo/years', methods=['GET'])
def get_available_years():
    """
    Returns a list of all years for which IPO data is available.
    """
    years = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for item in os.listdir(IPO_DATA_BASE_DIR):
            item_path = os.path.join(IPO_DATA_BASE_DIR, item)
            if os.path.isdir(item_path):
                try:
                    year = int(item)
                    # Only include years for which current_meta.json exists
                    if os.path.exists(os.path.join(item_path, 'current_meta.json')):
                        years.append(year)
                except ValueError:
                    app.logger.debug(f"Skipping non-numeric directory in IPO_DATA: {item}")
                    continue
    return jsonify(sorted(years, reverse=True))


@app.route('/api/ipo/all', methods=['GET'])
def get_all_ipos():
    """
    Returns a flattened list of all IPOs from all available years,
    with their basic metadata and calculated status. Includes the 'slug'.
    """
    all_ipos = []
    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year = int(year_str)
                years_to_process.append(year)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year):  # Ensure meta data is loaded/fresh
            for ipo_meta in ipo_cache[year]['meta_data']:
                # For basic list, we only need meta data and status (which requires ipo_details)
                ipo_data_for_status = get_ipo_detail_data(year, ipo_meta['json_path'])
                status = "Unknown"
                if ipo_data_for_status and "ipo_details" in ipo_data_for_status:
                    status = get_ipo_status(ipo_data_for_status["ipo_details"])
                else:
                    app.logger.debug(f"No 'ipo_details' found or failed to load data for {ipo_meta.get('name')} (for status).")

                all_ipos.append({
                    "name": ipo_meta.get("name"),
                    "slug": ipo_meta.get("slug"),
                    "url": ipo_meta.get("url"),
                    "html_path": ipo_meta.get("html_path"),
                    "json_path": ipo_meta.get("json_path"),
                    "year": year,
                    "status": status
                })
    return jsonify(all_ipos)


@app.route('/api/ipo/year/<int:year>', methods=['GET'])
def get_ipos_by_year(year):
    """
    Returns a list of all IPOs for a specific year,
    with their basic metadata and calculated status. Includes the 'slug'.
    """
    if not load_year_data(year):
        abort(404, description=f"No IPO data found for year {year}")

    ipos_in_year = []
    for ipo_meta in ipo_cache[year]['meta_data']:
        # For basic list, we only need meta data and status (which requires ipo_details)
        ipo_data_for_status = get_ipo_detail_data(year, ipo_meta['json_path'])
        status = "Unknown"
        if ipo_data_for_status and "ipo_details" in ipo_data_for_status:
            status = get_ipo_status(ipo_data_for_status["ipo_details"])
        else:
            app.logger.debug(f"No 'ipo_details' found or failed to load data for {ipo_meta.get('name')} in year {year} (for status).")

        ipos_in_year.append({
            "name": ipo_meta.get("name"),
            "slug": ipo_meta.get("slug"),
            "url": ipo_meta.get("url"),
            "html_path": ipo_meta.get("html_path"),
            "json_path": ipo_meta.get("json_path"),
            "year": year,
            "status": status
        })
    return jsonify(ipos_in_year)


@app.route('/api/ipo/details/<string:ipo_slug>', methods=['GET'])
def get_single_ipo_by_slug(ipo_slug):
    """
    Returns the complete data for a single IPO based on its slug,
    including its status. Optionally filters the response by specified keys.
    Query Parameters:
        fields (str, optional): Comma-separated list of keys to include in the response.
                                Supports dot notation for nested keys (e.g., 'company_contact_details.company_name').
                                Also supports array indexing (e.g., 'ipo_details.0.1').
    """
    found_ipo_meta = None
    target_year = None

    # First, find the IPO across all years using the slug
    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year_int = int(year_str)
                years_to_process.append(year_int)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year): # Ensure meta data is loaded
            for ipo_meta in ipo_cache[year]['meta_data']:
                if 'slug' in ipo_meta and ipo_meta['slug'] == ipo_slug:
                    found_ipo_meta = ipo_meta
                    target_year = year
                    break
            if found_ipo_meta:
                break

    if not found_ipo_meta:
        app.logger.error(f"IPO with slug '{ipo_slug}' not found across any loaded years.")
        abort(404, description=f"IPO with slug '{ipo_slug}' not found.")

    # This call will load the full IPO data into cache if not already present
    ipo_data = get_ipo_detail_data(target_year, found_ipo_meta['json_path'])
    if not ipo_data:
        app.logger.error(
            f"Failed to load detailed data for IPO with slug '{ipo_slug}' from path '{found_ipo_meta['json_path']}'.")
        abort(500, description=f"Failed to load detailed data for IPO with slug '{ipo_slug}'.")

    status = "Unknown"
    if "ipo_details" in ipo_data:
        status = get_ipo_status(ipo_data["ipo_details"])
    else:
        app.logger.debug(f"No 'ipo_details' found for detailed IPO data of {ipo_slug}")

    ipo_data['status'] = status  # Always append status

    # Handle 'fields' query parameter for filtering
    fields_param = request.args.get('fields')
    if fields_param:
        requested_fields = [f.strip() for f in fields_param.split(',')]
        filtered_response = {}
        for field_path in requested_fields:
            value = get_nested_value(ipo_data, field_path)
            # Reconstruct the nested structure for the response
            # This part needs careful handling to build nested dicts/lists
            temp_target = filtered_response
            path_parts = field_path.split('.')
            for i, part in enumerate(path_parts):
                if i == len(path_parts) - 1:
                    temp_target[part] = value
                else:
                    # If the next part is a digit, assume it's an array index
                    if i + 1 < len(path_parts) and path_parts[i+1].isdigit():
                        if part not in temp_target or not isinstance(temp_target[part], list):
                            temp_target[part] = []
                        # Ensure the list is long enough for the index
                        index = int(path_parts[i+1])
                        while len(temp_target[part]) <= index:
                            temp_target[part].append({}) # Append empty dicts as placeholders for nested dicts
                        temp_target = temp_target[part][index]
                    else:
                        if part not in temp_target or not isinstance(temp_target[part], dict):
                            temp_target[part] = {}
                        temp_target = temp_target[part]
        return jsonify(filtered_response)
    else:
        return jsonify(ipo_data)


@app.route('/api/ipo/status/<status_type>', methods=['GET'])
def get_ipos_by_status(status_type):
    """
    Returns IPOs filtered by status (upcoming, open, closed). Includes the 'slug'.
    """
    valid_statuses = {"upcoming", "open", "closed"}
    if status_type.lower() not in valid_statuses:
        abort(400, description=f"Invalid status type. Must be one of: {', '.join(valid_statuses)}")

    filtered_ipos = []
    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year = int(year_str)
                years_to_process.append(year)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year):
            for ipo_meta in ipo_cache[year]['meta_data']:
                # Need ipo_details for status calculation
                ipo_data_for_status = get_ipo_detail_data(year, ipo_meta['json_path'])
                status = "Unknown"
                if ipo_data_for_status and "ipo_details" in ipo_data_for_status:
                    status = get_ipo_status(ipo_data_for_status["ipo_details"])
                else:
                    app.logger.debug(f"No 'ipo_details' found or failed to load data for {ipo_meta.get('name')} (for status).")

                if status.lower() == status_type.lower():
                    filtered_ipos.append({
                        "name": ipo_meta.get("name"),
                        "slug": ipo_meta.get("slug"),
                        "url": ipo_meta.get("url"),
                        "html_path": ipo_meta.get("html_path"),
                        "json_path": ipo_meta.get("json_path"),
                        "year": year,
                        "status": status
                    })
    return jsonify(filtered_ipos)


@app.route('/api/ipo/search', methods=['GET'])
def search_ipos():
    """
    Searches for IPOs based on a query string in their name and company description.
    Query Parameters:
        query (str, required): The search term.
    Returns a list of matching IPOs with basic metadata, slug, and status.
    """
    search_query = request.args.get('query')
    if not search_query:
        abort(400, description="Missing 'query' parameter for search.")

    search_query_lower = search_query.lower()
    matching_ipos = []

    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year = int(year_str)
                years_to_process.append(year)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year):
            for ipo_meta in ipo_cache[year]['meta_data']:
                # Need ipo_details for status and about_company.description for search
                ipo_data_for_search = get_ipo_detail_data(year, ipo_meta['json_path'])
                status = "Unknown"
                if ipo_data_for_search and "ipo_details" in ipo_data_for_search:
                    status = get_ipo_status(ipo_data_for_search["ipo_details"])

                # Check name
                name_match = False
                if ipo_meta.get('name') and search_query_lower in ipo_meta['name'].lower():
                    name_match = True

                # Check company description (if available)
                description_match = False
                if ipo_data_for_search and 'about_company' in ipo_data_for_search and 'description' in ipo_data_for_search['about_company']:
                    if ipo_data_for_search['about_company']['description'] and \
                       search_query_lower in ipo_data_for_search['about_company']['description'].lower():
                        description_match = True

                if name_match or description_match:
                    matching_ipos.append({
                        "name": ipo_meta.get("name"),
                        "slug": ipo_meta.get("slug"),
                        "url": ipo_meta.get("url"),
                        "html_path": ipo_meta.get("html_path"),
                        "json_path": ipo_meta.get("json_path"),
                        "year": year,
                        "status": status
                    })
    return jsonify(matching_ipos)


@app.route('/api/ipo/overview', methods=['GET'])
def get_ipo_overview():
    """
    Provides a summary of IPOs, including counts for current year, upcoming, open, and closed IPOs.
    Optionally returns a limited list of IPOs for each status.
    Query Parameters:
        limit (int, optional): The maximum number of IPOs to return for each status list.
    """
    limit = request.args.get('limit', type=int)
    current_year = date.today().year

    total_ipos_current_year = 0
    upcoming_ipos = []
    open_ipos = []
    closed_ipos = []

    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year = int(year_str)
                years_to_process.append(year)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year):
            for ipo_meta in ipo_cache[year]['meta_data']:
                # Need ipo_details for status calculation
                ipo_data_for_status = get_ipo_detail_data(year, ipo_meta['json_path'])
                status = "Unknown"
                if ipo_data_for_status and "ipo_details" in ipo_data_for_status:
                    status = get_ipo_status(ipo_data_for_status["ipo_details"])

                ipo_entry = {
                    "name": ipo_meta.get("name"),
                    "slug": ipo_meta.get("slug"),
                    "url": ipo_meta.get("url"),
                    "html_path": ipo_meta.get("html_path"),
                    "json_path": ipo_meta.get("json_path"),
                    "year": year,
                    "status": status
                }

                # Categorize for counts and lists
                if year == current_year:
                    total_ipos_current_year += 1

                if status == "Upcoming":
                    upcoming_ipos.append(ipo_entry)
                elif status == "Open":
                    open_ipos.append(ipo_entry)
                elif status == "Closed":
                    closed_ipos.append(ipo_entry)

    # Apply limit if provided for the *lists* of IPOs returned
    limited_upcoming_ipos = upcoming_ipos[:limit] if limit is not None else upcoming_ipos
    limited_open_ipos = open_ipos[:limit] if limit is not None else open_ipos
    limited_closed_ipos = closed_ipos[:limit] if limit is not None else closed_ipos

    overview = {
        "total_ipos_current_year": total_ipos_current_year,
        "total_upcoming_ipos_count": len(upcoming_ipos), # Use len of full list for total count
        "total_open_ipos_count": len(open_ipos),         # Use len of full list for total count
        "total_closed_ipos_count": len(closed_ipos),     # Use len of full list for total count
        "upcoming_ipos_list": limited_upcoming_ipos,
        "open_ipos_list": limited_open_ipos,
        "closed_ipos_list": limited_closed_ipos
    }

    return jsonify(overview)


@app.route('/api/ipo/today', methods=['GET'])
def get_today_ipos():
    """
    Returns IPOs that are opening, closing, or listing today.
    """
    today = date.today()
    today_ipos = []

    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year = int(year_str)
                years_to_process.append(year)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year):
            for ipo_meta in ipo_cache[year]['meta_data']:
                # Need ipo_details for date checks and status
                ipo_data_for_today = get_ipo_detail_data(year, ipo_meta['json_path'])
                if not ipo_data_for_today or "ipo_details" not in ipo_data_for_today:
                    continue

                ipo_date_range_str = None
                listing_date_str = None
                for detail in ipo_data_for_today["ipo_details"]:
                    if detail[0] == "IPO Date":
                        ipo_date_range_str = detail[1]
                    elif detail[0] == "Listing Date":
                        listing_date_str = detail[1]

                is_today_relevant = False
                event_type = []

                # Check IPO Open/Close Dates
                if ipo_date_range_str:
                    date_match = re.match(r'(\w+ \d+, \d{4})to(\w+ \d+, \d{4})', ipo_date_range_str)
                    if date_match:
                        ipo_open_date = parse_date_robustly(date_match.group(1))
                        ipo_close_date = parse_date_robustly(date_match.group(2))
                    else:
                        ipo_open_date = parse_date_robustly(ipo_date_range_str)
                        ipo_close_date = ipo_open_date  # Single date

                    if ipo_open_date and ipo_close_date:
                        if ipo_open_date == today:
                            is_today_relevant = True
                            event_type.append("Opening Today")
                        if ipo_close_date == today:
                            is_today_relevant = True
                            event_type.append("Closing Today")

                # Check Listing Date
                if listing_date_str:
                    listing_date = parse_date_robustly(listing_date_str)
                    if listing_date == today:
                        is_today_relevant = True
                        event_type.append("Listing Today")

                if is_today_relevant:
                    ipo_entry = {
                        "name": ipo_meta.get("name"),
                        "slug": ipo_meta.get("slug"),
                        "url": ipo_meta.get("url"),
                        "html_path": ipo_meta.get("html_path"),
                        "json_path": ipo_meta.get("json_path"),
                        "year": year,
                        "status": get_ipo_status(ipo_data_for_today["ipo_details"]),  # Get current status
                        "today_events": event_type
                    }
                    today_ipos.append(ipo_entry)

    return jsonify(today_ipos)


@app.route('/api/ipo/listing-type/<string:listing_type>', methods=['GET'])
def get_ipos_by_listing_type(listing_type):
    """
    Returns IPOs filtered by their listing exchange (e.g., 'NSE SME', 'BSE Mainboard').
    URL Parameter:
        listing_type (str, required): The listing exchange (case-insensitive, e.g., 'nse sme').
    """
    target_listing_type_lower = listing_type.lower()
    filtered_ipos = []

    years_to_process = []
    if os.path.exists(IPO_DATA_BASE_DIR):
        for year_str in os.listdir(IPO_DATA_BASE_DIR):
            try:
                year = int(year_str)
                years_to_process.append(year)
            except ValueError:
                pass # Ignore non-numeric directory names

    for year in sorted(years_to_process, reverse=True):
        if load_year_data(year):
            for ipo_meta in ipo_cache[year]['meta_data']:
                # Need ipo_details to get 'Listing At'
                ipo_data_for_listing_type = get_ipo_detail_data(year, ipo_meta['json_path'])
                if not ipo_data_for_listing_type or "ipo_details" not in ipo_data_for_listing_type:
                    continue

                listing_at = None
                for detail in ipo_data_for_listing_type["ipo_details"]:
                    if detail[0] == "Listing At":
                        listing_at = detail[1]
                        break

                if listing_at and listing_at.lower() == target_listing_type_lower:
                    ipo_entry = {
                        "name": ipo_meta.get("name"),
                        "slug": ipo_meta.get("slug"),
                        "url": ipo_meta.get("url"),
                        "html_path": ipo_meta.get("html_path"),
                        "json_path": ipo_meta.get("json_path"),
                        "year": year,
                        "status": get_ipo_status(ipo_data_for_listing_type["ipo_details"]),
                        "listing_at": listing_at
                    }
                    filtered_ipos.append(ipo_entry)

    return jsonify(filtered_ipos)

# --- CACHING MECHANISMS ---

def clear_and_preload_cache():
    """
    Clears the entire IPO cache and then reloads only the meta data for all years.
    Individual IPO details are loaded lazily upon first access.
    """
    global ipo_cache
    app.logger.info("Clearing and pre-loading cache (meta data only)...")
    ipo_cache = {} # Clear the cache

    # Load all meta data for all available years
    available_years_for_meta = []
    if not os.path.exists(IPO_DATA_BASE_DIR):
        app.logger.error(f"Base IPO data directory not found: {IPO_DATA_BASE_DIR}. Cannot preload cache.")
        return

    for year_dir_name in os.listdir(IPO_DATA_BASE_DIR):
        try:
            year_int = int(year_dir_name)
            if load_year_data(year_int): # This loads the meta data for the year
                available_years_for_meta.append(year_int)
        except ValueError:
            app.logger.warning(f"Skipping non-numeric directory '{year_dir_name}' during cache preload (meta).")
        except Exception as e:
            app.logger.error(f"Error loading meta for year '{year_dir_name}' during preload: {e}")

    app.logger.info(f"Cache pre-loaded with meta data for {len(available_years_for_meta)} years.")
    app.logger.info("Individual IPO details will be loaded on demand.")


def start_cache_refresher():
    """
    Starts a background thread to periodically clear and preload the cache.
    """
    def refresher_task():
        while True:
            app.logger.info(f"Next cache refresh scheduled in {CACHE_REFRESH_INTERVAL_SECONDS / 3600} hours.")
            time.sleep(CACHE_REFRESH_INTERVAL_SECONDS)
            clear_and_preload_cache()

    # Daemon thread ensures it exits when the main program exits
    refresher_thread = threading.Thread(target=refresher_task, daemon=True)
    refresher_thread.start()
    app.logger.info("Cache refresher thread started.")

@app.route('/api/cache/clear', methods=['POST'])
def force_cache_clear_api():
    """
    API endpoint to manually clear and preload the cache.
    Use POST request to prevent accidental clearing via browser.
    """
    app.logger.info("Manual cache clear initiated via API.")
    clear_and_preload_cache()
    return jsonify({"message": "Cache cleared and meta-data pre-loaded successfully. Individual details will load on demand."}), 200

# --- MAIN APPLICATION START ---

if __name__ == '__main__':
    app.logger.info("Starting IPO API application...")

    # Initial clear and preload on startup to ensure meta-data cache is hot
    clear_and_preload_cache()
    # Start the background cache refresher
    start_cache_refresher()

    app.run(debug=True, host="0.0.0.0", port=1233, use_reloader=False) # use_reloader=False when using threading