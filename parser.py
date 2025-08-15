from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime


# --- Define explicit data structures for table components ---

class Cell:
    """Represents a single cell (td or th) in a table."""

    def __init__(self, text):
        self.text = text.strip()

    def __repr__(self):
        return f"Cell('{self.text}')"


class Row:
    """Represents a single row (tr) in a table."""

    def __init__(self, cells):
        self.cells = [Cell(text) for text in cells]

    @property
    def values(self):
        """Returns a list of text values from the cells in the row."""
        return [cell.text for cell in self.cells]

    def to_dict(self, headers):
        """Converts the row to a dictionary using provided headers."""
        if len(headers) == len(self.values):
            return dict(zip(headers, self.values))
        # Fallback to list if header count mismatch or no headers
        return self.values

    def __repr__(self):
        return f"Row({[cell.text for cell in self.cells]})"


class TableData:
    """
    Represents a parsed HTML table, with explicit headers and data rows.
    """

    def __init__(self, headers=None, data_rows=None):
        self.headers = Row(headers) if headers else None
        self.data_rows = [Row(row) for row in data_rows] if data_rows else []

    def to_list_of_dicts(self):
        """
        Converts the table data into a list of dictionaries.
        Each dictionary represents a row, with header names as keys.
        """
        if not self.headers:
            return [row.values for row in self.data_rows]

        header_values = self.headers.values
        structured_data = []
        for row in self.data_rows:
            structured_data.append(row.to_dict(header_values))
        return structured_data

    def __repr__(self):
        header_repr = f"Headers: {self.headers.values}\n" if self.headers else "No Headers\n"
        data_repr = "\n".join([f"  - {row.values}" for row in self.data_rows])
        return f"TableData(\n{header_repr}Data:\n{data_repr}\n)"


# --- Function to parse specific div sections ---

def parse_div_sections(soup):
    """
    Parses specific div structures for prospectus links, contact details,
    registrar info, and the 'About' section, using generic keywords.

    Args:
        soup (BeautifulSoup object): The parsed HTML content.

    Returns:
        dict: A dictionary containing extracted data from div sections.
    """
    div_data = {}
    prospectus_header_elem = None
    for header_div in soup.find_all('div', class_='card-header'):
        if "Prospectus" in header_div.get_text(strip=True):
            prospectus_header_elem = header_div
            break

    if prospectus_header_elem:
        prospectus_card = prospectus_header_elem.find_parent('div', class_='card')
        if prospectus_card:
            prospectus_links = []
            for li in prospectus_card.find_all('li'):
                a_tag = li.find('a')
                if a_tag:
                    href = a_tag.get('href', '').strip()
                    if "chittorgarh.net" in href:
                        continue  # Skip this link
                    prospectus_links.append({
                        'title': a_tag.get('title', '').strip(),
                        'href': href,
                        'text': a_tag.get_text(strip=True)
                    })
            if prospectus_links:
                div_data['prospectus_links'] = prospectus_links

    promoter_holding_header = None
    for h2 in soup.find_all('h2', itemprop='about'):
        if 'Promoter Holding' in h2.get_text(strip=True):
            promoter_holding_header = h2
            break

    if promoter_holding_header:
        promoter_section = promoter_holding_header.find_parent('div', itemtype='http://schema.org/Table')
        if promoter_section:
            promoter_info_div = promoter_section.find('div', class_='mb-2')
            if promoter_info_div:
                promoters_text = promoter_info_div.get_text(strip=True)
                pre_issue = post_issue = None
                table = promoter_section.find('table')
                if table:
                    for row in table.find_all('tr'):
                        cells = row.find_all('td')
                        if len(cells) == 2:
                            heading = cells[0].get_text(strip=True)
                            value = cells[1].get_text(strip=True)
                            if 'Pre Issue' in heading:
                                pre_issue = value
                            elif 'Post Issue' in heading:
                                post_issue = value
                div_data['promoters'] = promoters_text


    # --- Contact Details Section ---
    for card_header in soup.find_all('div', class_='card-header'):
        if "Contact Details" in card_header.get_text(strip=True):
            contact_card = card_header.find_parent('div', class_='card')
            if contact_card:
                address_tag = contact_card.find('address')
                if address_tag:
                    contact_info = {}
                    full_text = address_tag.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in full_text.split('\n') if line.strip()]

                    company_name = ""
                    address_parts = []
                    phone = ""
                    email = ""
                    website = ""

                    # Extract phone
                    phone_match = re.search(r'Phone\s*:\s*([+\d\s-]+)', full_text)
                    if phone_match:
                        phone = phone_match.group(1).strip()

                    # Extract email
                    email_match = re.search(r'Email\s*:\s*([\w\.-]+@[\w\.-]+)', full_text)
                    if email_match:
                        email = email_match.group(1).strip()

                    # Extract website
                    website_tag = address_tag.find('a', href=lambda href: href and "http" in href)
                    if website_tag:
                        website = website_tag['href'].strip()

                    # Parse lines for company name and address
                    for line in lines:
                        if "Phone:" in line or "Email:" in line or "Website:" in line or re.match(r'^[+\d\s-]+$',
                                                                                                  line) or '@' in line or 'http' in line:
                            continue
                        if not company_name:
                            company_name = line
                        else:
                            address_parts.append(line)

                    contact_info['company_name'] = company_name
                    contact_info['address'] = ", ".join(address_parts)
                    if phone: contact_info['phone'] = phone
                    if email: contact_info['email'] = email
                    if website: contact_info['website'] = website

                    if contact_info:
                        div_data['company_contact_details'] = contact_info
                    break  # Stop after first contact details found

    # --- Registrar Section ---
    for card_header in soup.find_all('div', class_='card-header'):
        if "Registrar" in card_header.get_text(strip=True):
            registrar_card = card_header.find_parent('div', class_='card')
            if registrar_card:
                registrar_info = {}
                p_tag = registrar_card.find('p')
                if p_tag:
                    # Registrar name
                    registrar_name_tag = p_tag.find('strong') or p_tag.find('a')
                    if registrar_name_tag:
                        registrar_info['name'] = registrar_name_tag.get_text(strip=True)

                    full_text = p_tag.get_text(separator='\n', strip=True)

                    # Phone
                    phone_match = re.search(r'Phone\s*:\s*([+\d\s-]+)', full_text)
                    if phone_match:
                        registrar_info['phone'] = phone_match.group(1).strip()

                    # Email
                    email_match = re.search(r'Email\s*:\s*([\w\.-]+@[\w\.-]+)', full_text)
                    if email_match:
                        registrar_info['email'] = email_match.group(1).strip()

                    # Website
                    website_tag = p_tag.find('a', href=lambda href: href and "http" in href)
                    if website_tag:
                        registrar_info['website'] = website_tag['href'].strip()

                if registrar_info:
                    div_data['ipo_registrar_details'] = registrar_info
            break  # Stop after first matching registrar section

    # --- About Company Section ---
    about_section_div = soup.find('div', class_='ipo-summary')
    if about_section_div:
        about_heading = about_section_div.find('h2', string=lambda text: text and text.strip().startswith("About"))
        if about_heading:
            ipo_summary_content = about_section_div.find('div', id='ipoSummary')
            if ipo_summary_content:
                about_text_paragraphs = [p.get_text(strip=True) for p in ipo_summary_content.find_all('p')]

                competitive_strengths = []
                ol_tag = ipo_summary_content.find('ol')
                if ol_tag:
                    competitive_strengths = [li.get_text(strip=True) for li in ol_tag.find_all('li')]

                about_info = {
                    'description': " ".join(about_text_paragraphs).replace('\n', ' ').replace('\r', '').strip(),
                    'competitive_strengths': competitive_strengths
                }
                div_data['about_company'] = about_info
    # --- Lead Manager(s) Section ---
    for card_header in soup.find_all('div', class_='card-header'):
        if "Lead Manager" in card_header.get_text(strip=True):
            lead_mgr_card = card_header.find_parent('div', class_='card')
            if lead_mgr_card:
                lead_managers = []
                # Only extract <li> elements inside <ol> (not <ul> which are reports)
                ol_tag = lead_mgr_card.find('ol')
                if ol_tag:
                    for li in ol_tag.find_all('li'):
                        a_tag = li.find('a')
                        if a_tag:
                            lead_managers.append({
                                'name': a_tag.get_text(strip=True),
                                'profile_link': a_tag.get('href', '').strip(),
                                'title': a_tag.get('title', '').strip()
                            })
                if lead_managers:
                    div_data['ipo_lead_managers'] = lead_managers
            break  # Stop after first match

    return div_data


# --- Main Parsing Function ---

def calculate_listing_gain(parsed_data):
    """
    Calculates the listing gain percentage from the listing day trading data.

    Formula: Listing Gain (%) = ((Open Price - Issue Price) / Issue Price) × 100

    Args:
        parsed_data (dict): The parsed data containing listing_day_trading information

    Returns:
        tuple: (listing_gain_percentage, calculation_details) or (None, None) if cannot calculate
    """
    if 'listing_day_trading' not in parsed_data:
        return None, None

    listing_data = parsed_data['listing_day_trading']
    if not isinstance(listing_data, list):
        return None, None

    issue_price = None
    open_price = None

    # Extract prices from the listing day trading data
    for entry in listing_data:
        if isinstance(entry, dict):
            price_detail = entry.get('Price Details', '').lower()

            # Look for issue price (can be "Final Issue Price" or "Issue Price")
            if 'issue price' in price_detail:
                price_value = entry.get('NSE SME', '') or entry.get('BSE', '') or entry.get('NSE', '')
                if price_value:
                    # Extract numeric value from price string (remove ₹ and other characters)
                    price_match = re.search(r'[\d,]+\.?\d*', price_value.replace(',', ''))
                    if price_match:
                        try:
                            issue_price = float(price_match.group())
                        except ValueError:
                            pass

            # Look for open price
            elif 'open' in price_detail:
                price_value = entry.get('NSE SME', '') or entry.get('BSE', '') or entry.get('NSE', '')
                if price_value:
                    # Extract numeric value from price string
                    price_match = re.search(r'[\d,]+\.?\d*', price_value.replace(',', ''))
                    if price_match:
                        try:
                            open_price = float(price_match.group())
                        except ValueError:
                            pass

    # Calculate listing gain if both prices are available
    if issue_price and open_price and issue_price > 0:
        listing_gain = ((open_price - issue_price) / issue_price) * 100
        calculation_details = {
            'formula': 'Listing Gain (%) = ((Open Price - Issue Price) / Issue Price) × 100',
            'open_price': open_price,
            'issue_price': issue_price,
            'calculation': f'(({open_price} - {issue_price}) / {issue_price}) × 100 = {listing_gain:.2f}%'
        }
        return round(listing_gain, 2), calculation_details

    return None, None


def parse_html_content(html_content):
    """
    Parses all <table> elements and specific div sections from the provided HTML.

    Args:
        html_content (str): The HTML content as a string.

    Returns:
        dict: A dictionary containing structured data from both tables and div sections.
    """

    soup = BeautifulSoup(html_content, 'html.parser')
    all_parsed_data = {}
    table_counter = 1

    # =====================================================================
    # CUSTOM KEY MAPPING LOGIC FOR TABLES - DEFINE YOUR RULES HERE
    # Map your desired output key to a LIST of potential search strings.
    # The first match in the list will determine the table's key.
    # Searches in H2 heading first, then in table's full text.
    # =====================================================================
    key_mapping_rules_tables = {
        'ipo_details': ['IPO Details', 'Face Value'],
        'reservation': ["Maximum Allottees", "Anchor Investor Shares Offered", "Investor Category"],
        'anchor_investors': ['Anchor lock-in period', 'Bid Date'],
        'timeline': ["Initiation of Refunds", "Cut-off time for UPI"],
        'lots': ['Lot Size Calculator', 'Retail (Min)', "Retail (Max)"],
        'promoters_holdings': ["Share Holding Pre Issue", "Share Holding Post Issue"],
        'company_financials': ["Amount in ₹ Crore", 'Assets', 'Total Borrowing'],
        'KPI': ['ROE', 'KPI'],
        'EPS': ["EPS (Rs)", "Post IPO"],
        'bidding_details': ["Subscription (times)", "Shares bid for"],
        'listing_details': ["ISIN", "NSE Symbol", "BSE Script Code"],
        'listing_day_trading': ['Last Trade', "Price Details"],
        'review': ["Brokers"],
        'objectives': ["Objects of the Issue", "Expected Amount (in Millions)"],
        'dhrp_status': ["Filed with SEBI/Exchange", "Description", "Addendum to DRHP"]
    }
    # =====================================================================

    # --- Parse Tables ---
    tables = soup.find_all('table')
    for table_elem in tables:
        table_key = str(table_counter)  # Default key
        table_full_text = table_elem.get_text()

        # Attempt to find a preceding H2 for mapping
        associated_header = None
        for sib in table_elem.find_previous_siblings():
            if sib.name == 'h2':
                associated_header = sib
                break

        # Check for matches in H2 heading first
        if associated_header:
            header_text = associated_header.get_text(strip=True)
            for custom_key, search_strings in key_mapping_rules_tables.items():
                for s_string in search_strings:
                    if s_string in header_text:
                        table_key = custom_key
                        break  # Found a match for this table
                if table_key != str(table_counter):  # If a match was found, break outer loop
                    break

        # Fallback to checking table's full text content if no H2 match was found
        if table_key == str(table_counter):  # If key is still default numeric
            for custom_key, search_strings in key_mapping_rules_tables.items():
                for s_string in search_strings:
                    if s_string in table_full_text:
                        table_key = custom_key
                        break  # Found a match for this table
                if table_key != str(table_counter):  # If a match was found, break outer loop
                    break

        extracted_headers = []
        extracted_data_rows = []

        # Prioritize headers from <thead>
        thead = table_elem.find('thead')
        if thead:
            header_ths = thead.find_all('th')
            extracted_headers = [th.get_text(strip=True) for th in header_ths]

        # Get all rows, then decide which are data rows
        all_trs = table_elem.find_all('tr')
        data_trs = []

        if extracted_headers:
            # If headers were found in thead, all other trs are data rows
            data_trs = [tr for tr in all_trs if tr.find_parent('thead') is None]
        else:
            # If no thead, try to infer headers from the first row if it contains <th>
            if all_trs and all_trs[0].find('th'):
                extracted_headers = [th.get_text(strip=True) for th in all_trs[0].find_all('th')]
                data_trs = all_trs[1:]  # Skip the first row as it's headers
            else:
                data_trs = all_trs  # All rows are data if no clear headers

        for tr in data_trs:
            cols = tr.find_all(['td', 'th'])
            col_values = [ele.get_text(strip=True) for ele in cols]
            if col_values:
                # Basic padding for rows with fewer columns than headers (e.g., merged cells)
                if extracted_headers and len(col_values) < len(extracted_headers):
                    col_values.extend([''] * (len(extracted_headers) - len(col_values)))
                extracted_data_rows.append(col_values)

        # Skip empty tables (e.g., ad placeholders or tables with no discernible data)
        if not extracted_data_rows and not extracted_headers:
            continue

        structured_table = TableData(headers=extracted_headers, data_rows=extracted_data_rows)
        final_table_output = structured_table.to_list_of_dicts()

        # Handle duplicate keys by appending a suffix
        original_table_key = table_key
        suffix_counter = 1
        while table_key in all_parsed_data:
            table_key = f"{original_table_key}_{suffix_counter}"
            suffix_counter += 1

        all_parsed_data[table_key] = final_table_output
        table_counter += 1

    # --- Parse Specific Div Sections ---
    div_sections_data = parse_div_sections(soup)
    all_parsed_data.update(div_sections_data)  # Add div data to the main dictionary

    return all_parsed_data


def process_meta_json():
    """
    Loads the meta JSON file, processes each HTML file, saves parsed JSON,
    and updates the meta file with JSON paths.
    """

    def get_price(price_list, price_detail_key):
        """
        Extracts the price as float for the given price_detail_key from the list of dicts.
        Checks keys in this priority order: NSE, BSE, NSE SME, BSE SME.
        Returns None if no valid price found or conversion fails.
        """
        preferred_keys = ['NSE', 'BSE', 'NSE SME', 'BSE SME']

        for entry in price_list:
            if entry.get('Price Details', '').strip().lower() == price_detail_key.lower():
                for key in preferred_keys:
                    price_str = entry.get(key)
                    if price_str:
                        # Clean the price string: remove currency symbols, commas, spaces
                        clean_price = price_str.replace('₹', '').replace(',', '').strip()
                        try:
                            return float(clean_price)
                        except ValueError:
                            return None
        return None


    current_year = datetime.now().year
    meta_file_path = f"IPO_DATA/{current_year}/current_meta.json"

    # Check if meta file exists
    if not os.path.exists(meta_file_path):
        print(f"Error: Meta file '{meta_file_path}' not found.")
        return

    # Load meta data
    try:
        with open(meta_file_path, 'r', encoding='utf-8') as f:
            meta_data = json.load(f)
    except Exception as e:
        print(f"Error loading meta file: {e}")
        return

    # Create json directory if it doesn't exist
    json_dir = f"IPO_DATA/{current_year}/json"
    os.makedirs(json_dir, exist_ok=True)

    # Process each IPO entry
    for entry in meta_data:
        ipo_name = entry['name']
        html_path = entry['html_path']


        # Full path to HTML file
        html_path_clean = html_path.replace(f"{current_year}/", "") if html_path else ""
        full_html_path = os.path.join("IPO_DATA", str(current_year), html_path_clean)

        if not os.path.exists(full_html_path):
            print(f"Warning: HTML file '{full_html_path}' not found for {ipo_name}")
            continue

        try:
            # Read and parse HTML file
            with open(full_html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()

            parsed_data = parse_html_content(html_content)


            # Create JSON filename (sanitize IPO name for filename)
            json_filename = re.sub(r'[^\w\s-]', '', ipo_name).strip()
            json_filename = re.sub(r'[-\s]+', '_', json_filename) + '.json'
            json_file_path = os.path.join(json_dir, json_filename)

            # Calculate listing gain percent
            issue_price = get_price(parsed_data.get('listing_day_trading', []), 'Final Issue Price')
            open_price = get_price(parsed_data.get('listing_day_trading', []), 'Open')

            if issue_price is not None and open_price is not None and issue_price != 0:
                gain_percent = round(((open_price - issue_price) / issue_price) * 100, 2)
                parsed_data['listing_gain_percent'] = f"{gain_percent}%"
            else:
                parsed_data['listing_gain_percent'] = None

            # Save parsed data to JSON file
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(parsed_data, json_file, indent=2, ensure_ascii=False)

            # Update meta entry with JSON path
            entry['json_path'] = f"{current_year}/json/{json_filename}"

            print(f"✓ Processed: {ipo_name} -> {json_filename}")

        except Exception as e:
            print(f"✗ Error processing {ipo_name}: {e}")
            continue

        # Save updated meta data after processing all entries
        try:
            with open(meta_file_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, indent=2, ensure_ascii=False)
            print(f"\n✓ Updated meta file: {meta_file_path}")
        except Exception as e:
            print(f"✗ Error updating meta file: {e}")

if __name__ == "__main__":
    # Check if running in batch mode (processing meta file) or single file mode

        # Batch processing mode
        process_meta_json()
