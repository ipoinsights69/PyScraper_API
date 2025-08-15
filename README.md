# IPO Scraper API Documentation

A RESTful API service that provides comprehensive information about Initial Public Offerings (IPOs) in India.

## Base URL
```
http://localhost:1234/api
```

## API Endpoints

### 1. Get IPO Overview
Returns a summary of all IPOs including counts and details for upcoming, open, and closed IPOs.

```http
GET /ipo/overview
```

Query Parameters:
- `limit` (optional): Number of IPOs to return per category

Response Example:
```json
{
  "total_ipos_current_year": 150,
  "total_upcoming_ipos_count": 45,
  "total_open_ipos_count": 5,
  "total_closed_ipos_count": 100,
  "upcoming_ipos_list": [
    {
      "name": "Example IPO Ltd",
      "slug": "example-ipo",
      "url": "https://example.com/ipo",
      "year": 2025,
      "status": "Upcoming",
      "issue_price": 500.0,
      "listing_price": null,
      "lot_size": 30,
      "listing_gain": null,
      "open_date": "2025-06-15",
      "close_date": "2025-06-18",
      "listing_date": null
    }
  ],
  "open_ipos_list": [...],
  "closed_ipos_list": [...]
}
```

### 2. Get IPO Details
Returns detailed information about a specific IPO.

```http
GET /ipo/details/{ipo-slug}
```

Path Parameters:
- `ipo-slug`: The URL-friendly slug of the IPO

Query Parameters:
- `fields` (optional): Comma-separated list of fields to include in response (supports dot notation)

Example:
```http
GET /ipo/details/example-ipo?fields=name,ipo_details,about_company.description
```

### 3. Search IPOs
Search for IPOs by name or description.

```http
GET /ipo/search?query={search-term}
```

Query Parameters:
- `query` (required): Search term to match against IPO names and descriptions

Response Example:
```json
[
  {
    "name": "Example IPO Ltd",
    "slug": "example-ipo",
    "url": "https://example.com/ipo",
    "html_path": "IPO_DATA/2025/html/Example_IPO.html",
    "json_path": "IPO_DATA/2025/json/Example_IPO.json",
    "year": 2025,
    "status": "Upcoming"
  }
]
```

### 4. Get IPOs by Status
Returns IPOs filtered by their current status.

```http
GET /ipo/status/{status-type}
```

Path Parameters:
- `status-type`: One of: "upcoming", "open", "closed"

### 5. Get Today's IPOs
Returns IPOs that are opening, closing, or listing today.

```http
GET /ipo/today
```

Response Example:
```json
[
  {
    "name": "Example IPO Ltd",
    "slug": "example-ipo",
    "url": "https://example.com/ipo",
    "year": 2025,
    "status": "Open",
    "today_events": ["Opening Today"]
  }
]
```

### 6. Get IPOs by Year
Returns all IPOs for a specific year.

```http
GET /ipo/year/{year}
```

Path Parameters:
- `year`: The year to get IPOs for (e.g., 2025)

### 7. Get Available Years
Returns a list of all years for which IPO data is available.

```http
GET /ipo/years
```

### 8. Get All IPOs
Returns a list of all IPOs across all years.

```http
GET /ipo/all
```

### 9. Get IPOs by Listing Type
Returns IPOs filtered by their listing exchange.

```http
GET /ipo/listing-type/{listing-type}
```

Path Parameters:
- `listing-type`: The listing exchange (e.g., "NSE SME", "BSE Mainboard")

### 10. Cache Management
Force a cache refresh.

```http
POST /api/cache/clear
```

## Response Formats

All successful responses are returned in JSON format with appropriate HTTP status codes.

### Success Response Format
```json
{
  "data": [...],
  "status": "success"
}
```

### Error Response Format
```json
{
  "description": "Error message describing what went wrong",
  "status": "error"
}
```

## HTTP Status Codes

- `200 OK`: Request successful
- `400 Bad Request`: Invalid request parameters
- `404 Not Found`: Requested resource not found
- `500 Internal Server Error`: Server-side error

## Rate Limiting

Currently, there are no rate limits implemented on the API.

## Caching

The API implements an in-memory cache with the following characteristics:
- Meta-data is pre-loaded and refreshed every 4 hours
- Individual IPO details are loaded on demand
- Manual cache refresh available via the `/api/cache/clear` endpoint

## Data Updates

IPO data is updated regularly to reflect:
- New IPO announcements
- Status changes
- Price updates
- Subscription details
- Listing information

## Best Practices

1. Use the `fields` parameter to request only needed data
2. Implement proper error handling for failed requests
3. Cache responses on the client side when appropriate
4. Use the slug-based endpoints for consistent results

## Example Usage (cURL)

Get overview of all IPOs:
```bash
curl http://localhost:1234/api/ipo/overview
```

Search for IPOs:
```bash
curl http://localhost:1234/api/ipo/search?query=technologies
```

Get specific IPO details:
```bash
curl http://localhost:1234/api/ipo/details/example-ipo
```

Get today's IPO activity:
```bash
curl http://localhost:1234/api/ipo/today
```
