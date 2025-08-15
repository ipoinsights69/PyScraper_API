# IPO Scraper API Documentation

## Base URL
```
http://localhost:1234/api
```

## Common Headers
All requests should include:
```
Accept: application/json
Content-Type: application/json
```

## Common Response Headers
```
Content-Type: application/json
Cache-Control: no-cache, no-store, must-revalidate
```

## Available Endpoints

### 1. Get Available Years
Returns a list of all years for which IPO data is available.

**Endpoint:**
```
GET /ipo/years
```

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/years" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[2024, 2023, 2022]
```

### 2. Get All IPOs
Returns a flattened list of all IPOs from all available years with basic metadata.

**Endpoint:**
```
GET /ipo/all
```

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/all" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[
  {
    "name": "Exitel Technologies Ltd",
    "slug": "exitel-technologies-ltd",
    "url": "https://example.com/ipo/exitel-tech",
    "html_path": "2024/html/Exitel_Technologies_Ltd.html",
    "json_path": "2024/json/Exitel_Technologies_Ltd.json",
    "year": 2024,
    "status": "Open"
  },
  {
    "name": "GreenEnergy Solutions Ltd",
    "slug": "greenenergy-solutions-ltd",
    "url": "https://example.com/ipo/green-energy",
    "html_path": "2024/html/GreenEnergy_Solutions_Ltd.html",
    "json_path": "2024/json/GreenEnergy_Solutions_Ltd.json",
    "year": 2024,
    "status": "Upcoming"
  }
]
```

### 3. Get IPOs by Year
Returns all IPOs for a specific year.

**Endpoint:**
```
GET /ipo/year/{year}
```

**Parameters:**
- `year` (path parameter, required): Integer year (e.g., 2024)

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/year/2024" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[
  {
    "name": "Exitel Technologies Ltd",
    "slug": "exitel-technologies-ltd",
    "url": "https://example.com/ipo/exitel-tech",
    "html_path": "2024/html/Exitel_Technologies_Ltd.html",
    "json_path": "2024/json/Exitel_Technologies_Ltd.json",
    "year": 2024,
    "status": "Open"
  }
]
```

**Error Response (404 Not Found):**
```json
{
  "description": "No IPO data found for year 2024"
}
```

### 4. Get Single IPO Details
Returns complete data for a single IPO based on its slug.

**Endpoint:**
```
GET /ipo/details/{ipo_slug}
```

**Parameters:**
- `ipo_slug` (path parameter, required): The slug identifier for the IPO
- `fields` (query parameter, optional): Comma-separated list of specific fields to return

**Sample Requests:**

1. Full Details:
```bash
curl -X GET "http://localhost:1234/api/ipo/details/exitel-technologies-ltd" \
  -H "Accept: application/json"
```

2. Specific Fields:
```bash
curl -X GET "http://localhost:1234/api/ipo/details/exitel-technologies-ltd?fields=company_contact_details.company_name,ipo_details.0.1" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**

1. Full Details:
```json
{
  "name": "Exitel Technologies Ltd",
  "about_company": {
    "description": "Leading provider of cloud solutions and IT services",
    "other_details": {
      "founded": "2015",
      "industry": "Information Technology",
      "key_products": ["Cloud Services", "IT Consulting"]
    }
  },
  "company_contact_details": {
    "company_name": "Exitel Technologies Ltd",
    "address": "Tech Park, Sector 15, Gurugram",
    "phone": "+91-124-4567890",
    "email": "info@exitel-tech.com",
    "website": "www.exitel-tech.com"
  },
  "ipo_details": [
    ["IPO Date", "May 14, 2024toMay 16, 2024"],
    ["Issue Type", "Book Built Issue IPO"],
    ["Listing At", "NSE SME"],
    ["Issue Size", "₹150.00 Cr"],
    ["Price Band", "₹250.00 to ₹275.00"],
    ["Market Lot", "50 Shares"],
    ["Issue Size Shares", "5454545 Shares"],
    ["Fresh Issue", "₹150.00 Cr"],
    ["Retail Quota", "35%"],
    ["QIB Quota", "50%"],
    ["NII Quota", "15%"]
  ],
  "subscription_details": {
    "retail": "2.5x",
    "qib": "3.2x",
    "nii": "1.8x",
    "total": "2.8x"
  },
  "important_dates": {
    "issue_opening": "2024-05-14",
    "issue_closing": "2024-05-16",
    "allotment_date": "2024-05-20",
    "refund_date": "2024-05-21",
    "listing_date": "2024-05-24"
  },
  "status": "Open"
}
```

2. Filtered Fields:
```json
{
  "company_contact_details": {
    "company_name": "Exitel Technologies Ltd"
  },
  "ipo_details": [
    ["Issue Type", "Book Built Issue IPO"]
  ]
}
```

**Error Response (404 Not Found):**
```json
{
  "description": "IPO with slug 'exitel-technologies-ltd' not found"
}
```

### 5. Get IPOs by Status
Returns IPOs filtered by their current status.

**Endpoint:**
```
GET /ipo/status/{status_type}
```

**Parameters:**
- `status_type` (path parameter, required): One of: "upcoming", "open", "closed"

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/status/open" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[
  {
    "name": "Exitel Technologies Ltd",
    "slug": "exitel-technologies-ltd",
    "url": "https://example.com/ipo/exitel-tech",
    "html_path": "2024/html/Exitel_Technologies_Ltd.html",
    "json_path": "2024/json/Exitel_Technologies_Ltd.json",
    "year": 2024,
    "status": "Open"
  }
]
```

**Error Response (400 Bad Request):**
```json
{
  "description": "Invalid status type. Must be one of: upcoming, open, closed"
}
```

### 6. Search IPOs
Searches for IPOs based on a query string in their name and company description.

**Endpoint:**
```
GET /ipo/search
```

**Parameters:**
- `query` (query parameter, required): Search term to match against IPO names and descriptions

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/search?query=technology" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[
  {
    "name": "Exitel Technologies Ltd",
    "slug": "exitel-technologies-ltd",
    "url": "https://example.com/ipo/exitel-tech",
    "html_path": "2024/html/Exitel_Technologies_Ltd.html",
    "json_path": "2024/json/Exitel_Technologies_Ltd.json",
    "year": 2024,
    "status": "Open"
  }
]
```

### 7. Get IPO Overview
Provides a summary of IPOs, including counts and optional lists for each status.

**Endpoint:**
```
GET /ipo/overview
```

**Parameters:**
- `limit` (query parameter, optional): Maximum number of IPOs to return for each status list

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/overview?limit=2" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
{
  "total_ipos_current_year": 50,
  "total_upcoming_ipos_count": 10,
  "total_open_ipos_count": 5,
  "total_closed_ipos_count": 35,
  "upcoming_ipos_list": [
    {
      "name": "GreenEnergy Solutions Ltd",
      "slug": "greenenergy-solutions-ltd",
      "url": "https://example.com/ipo/green-energy",
      "html_path": "2024/html/GreenEnergy_Solutions_Ltd.html",
      "json_path": "2024/json/GreenEnergy_Solutions_Ltd.json",
      "year": 2024,
      "status": "Upcoming"
    }
  ],
  "open_ipos_list": [
    {
      "name": "Exitel Technologies Ltd",
      "slug": "exitel-technologies-ltd",
      "url": "https://example.com/ipo/exitel-tech",
      "html_path": "2024/html/Exitel_Technologies_Ltd.html",
      "json_path": "2024/json/Exitel_Technologies_Ltd.json",
      "year": 2024,
      "status": "Open"
    }
  ],
  "closed_ipos_list": [
    {
      "name": "IndiaFin Services Ltd",
      "slug": "indiafin-services-ltd",
      "url": "https://example.com/ipo/indiafin",
      "html_path": "2024/html/IndiaFin_Services_Ltd.html",
      "json_path": "2024/json/IndiaFin_Services_Ltd.json",
      "year": 2024,
      "status": "Closed"
    }
  ]
}
```

### 8. Get Today's IPOs
Returns IPOs that are opening, closing, or listing today.

**Endpoint:**
```
GET /ipo/today
```

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/today" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[
  {
    "name": "Exitel Technologies Ltd",
    "slug": "exitel-technologies-ltd",
    "url": "https://example.com/ipo/exitel-tech",
    "html_path": "2024/html/Exitel_Technologies_Ltd.html",
    "json_path": "2024/json/Exitel_Technologies_Ltd.json",
    "year": 2024,
    "status": "Open",
    "today_events": ["Opening Today"]
  },
  {
    "name": "IndiaFin Services Ltd",
    "slug": "indiafin-services-ltd",
    "url": "https://example.com/ipo/indiafin",
    "html_path": "2024/html/IndiaFin_Services_Ltd.html",
    "json_path": "2024/json/IndiaFin_Services_Ltd.json",
    "year": 2024,
    "status": "Closed",
    "today_events": ["Listing Today"]
  }
]
```

### 9. Get IPOs by Listing Type
Returns IPOs filtered by their listing exchange.

**Endpoint:**
```
GET /ipo/listing-type/{listing_type}
```

**Parameters:**
- `listing_type` (path parameter, required): The listing exchange (e.g., "NSE SME", "BSE Mainboard")

**Sample Request:**
```bash
curl -X GET "http://localhost:1234/api/ipo/listing-type/NSE%20SME" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
[
  {
    "name": "Exitel Technologies Ltd",
    "slug": "exitel-technologies-ltd",
    "url": "https://example.com/ipo/exitel-tech",
    "html_path": "2024/html/Exitel_Technologies_Ltd.html",
    "json_path": "2024/json/Exitel_Technologies_Ltd.json",
    "year": 2024,
    "status": "Open",
    "listing_at": "NSE SME"
  }
]
```

### 10. Clear Cache (Admin Endpoint)
Manually clear and reload the cache.

**Endpoint:**
```
POST /cache/clear
```

**Sample Request:**
```bash
curl -X POST "http://localhost:1234/api/cache/clear" \
  -H "Accept: application/json"
```

**Success Response (200 OK):**
```json
{
  "message": "Cache cleared and meta-data pre-loaded successfully. Individual details will load on demand."
}
```

## Status Types
IPOs can have the following status types:
- `Upcoming`: IPO dates are in the future
- `Open`: IPO is currently open for subscription
- `Closed`: IPO subscription period has ended
- `Unknown`: Status could not be determined

## Error Handling

### Common Error Responses

1. **400 Bad Request**
```json
{
  "description": "Invalid parameters or missing required fields"
}
```

2. **404 Not Found**
```json
{
  "description": "Requested resource not found"
}
```

3. **500 Internal Server Error**
```json
{
  "description": "An unexpected error occurred while processing your request"
}
```

## Data Formats

### Date Formats
- All dates in responses are in the format "MMM DD, YYYY" (e.g., "May 14, 2024")
- Date fields in the detailed IPO response use ISO 8601 format (YYYY-MM-DD)

### Numerical Values
- Currency values are in Indian Rupees (₹)
- Subscription ratios are expressed as multipliers (e.g., "2.5x")
- Percentages are expressed as strings with % symbol (e.g., "35%")

### Slugs
- Generated from company names
- Lowercase, URL-friendly
- Special characters removed
- Spaces replaced with hyphens
- Example: "Exitel Technologies Ltd" → "exitel-technologies-ltd"

## Caching
- Cache refreshes automatically every 4 hours
- Manual cache refresh available via `/api/cache/clear` endpoint
- Individual IPO details are loaded lazily on first access

## Rate Limiting
- No rate limiting implemented currently
- Consider implementing rate limiting for production use

## Best Practices
1. Always check the status code of the response
2. Handle errors gracefully in your application
3. Use appropriate error handling for network issues
4. Cache responses on the client side when appropriate
5. Use the fields parameter to reduce response size when only specific data is needed 