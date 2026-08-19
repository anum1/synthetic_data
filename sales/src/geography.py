"""Fixed geography catalog: region -> country -> state/city with coordinates."""

# (region, country, country_code, currency, state, city, lat, lon)
CITIES = [
    # ---- North America ----
    ("North America", "United States", "US", "USD", "California", "San Francisco", 37.7749, -122.4194),
    ("North America", "United States", "US", "USD", "California", "Los Angeles", 34.0522, -118.2437),
    ("North America", "United States", "US", "USD", "California", "San Diego", 32.7157, -117.1611),
    ("North America", "United States", "US", "USD", "Texas", "Dallas", 32.7767, -96.7970),
    ("North America", "United States", "US", "USD", "Texas", "Austin", 30.2672, -97.7431),
    ("North America", "United States", "US", "USD", "Texas", "Houston", 29.7604, -95.3698),
    ("North America", "United States", "US", "USD", "New York", "New York", 40.7128, -74.0060),
    ("North America", "United States", "US", "USD", "New York", "Buffalo", 42.8864, -78.8784),
    ("North America", "United States", "US", "USD", "Illinois", "Chicago", 41.8781, -87.6298),
    ("North America", "United States", "US", "USD", "Georgia", "Atlanta", 33.7490, -84.3880),
    ("North America", "United States", "US", "USD", "Washington", "Seattle", 47.6062, -122.3321),
    ("North America", "United States", "US", "USD", "Massachusetts", "Boston", 42.3601, -71.0589),
    ("North America", "United States", "US", "USD", "Florida", "Miami", 25.7617, -80.1918),
    ("North America", "United States", "US", "USD", "Colorado", "Denver", 39.7392, -104.9903),
    ("North America", "United States", "US", "USD", "Arizona", "Phoenix", 33.4484, -112.0740),
    ("North America", "Canada", "CA", "CAD", "Ontario", "Toronto", 43.6532, -79.3832),
    ("North America", "Canada", "CA", "CAD", "Quebec", "Montreal", 45.5017, -73.5673),
    ("North America", "Canada", "CA", "CAD", "British Columbia", "Vancouver", 49.2827, -123.1207),
    ("North America", "Canada", "CA", "CAD", "Alberta", "Calgary", 51.0447, -114.0719),

    # ---- Europe ----
    ("Europe", "Germany", "DE", "EUR", "Bavaria", "Munich", 48.1351, 11.5820),
    ("Europe", "Germany", "DE", "EUR", "Berlin", "Berlin", 52.5200, 13.4050),
    ("Europe", "Germany", "DE", "EUR", "Hesse", "Frankfurt", 50.1109, 8.6821),
    ("Europe", "Germany", "DE", "EUR", "North Rhine-Westphalia", "Cologne", 50.9375, 6.9603),
    ("Europe", "Germany", "DE", "EUR", "Hamburg", "Hamburg", 53.5511, 9.9937),
    ("Europe", "United Kingdom", "GB", "GBP", "England", "London", 51.5074, -0.1278),
    ("Europe", "United Kingdom", "GB", "GBP", "England", "Manchester", 53.4808, -2.2426),
    ("Europe", "United Kingdom", "GB", "GBP", "Scotland", "Edinburgh", 55.9533, -3.1883),
    ("Europe", "France", "FR", "EUR", "Ile-de-France", "Paris", 48.8566, 2.3522),
    ("Europe", "France", "FR", "EUR", "Auvergne-Rhone-Alpes", "Lyon", 45.7640, 4.8357),
    ("Europe", "Netherlands", "NL", "EUR", "North Holland", "Amsterdam", 52.3676, 4.9041),
    ("Europe", "Spain", "ES", "EUR", "Madrid", "Madrid", 40.4168, -3.7038),
    ("Europe", "Spain", "ES", "EUR", "Catalonia", "Barcelona", 41.3874, 2.1686),
    ("Europe", "Italy", "IT", "EUR", "Lombardy", "Milan", 45.4642, 9.1900),
    ("Europe", "Italy", "IT", "EUR", "Lazio", "Rome", 41.9028, 12.4964),
    ("Europe", "Sweden", "SE", "EUR", "Stockholm", "Stockholm", 59.3293, 18.0686),
    ("Europe", "Poland", "PL", "EUR", "Masovia", "Warsaw", 52.2297, 21.0122),
    ("Europe", "Switzerland", "CH", "EUR", "Zurich", "Zurich", 47.3769, 8.5417),

    # ---- APAC ----
    ("APAC", "Japan", "JP", "JPY", "Tokyo", "Tokyo", 35.6762, 139.6503),
    ("APAC", "Japan", "JP", "JPY", "Osaka", "Osaka", 34.6937, 135.5023),
    ("APAC", "China", "CN", "CNY", "Shanghai", "Shanghai", 31.2304, 121.4737),
    ("APAC", "China", "CN", "CNY", "Beijing", "Beijing", 39.9042, 116.4074),
    ("APAC", "China", "CN", "CNY", "Guangdong", "Shenzhen", 22.5431, 114.0579),
    ("APAC", "India", "IN", "INR", "Karnataka", "Bengaluru", 12.9716, 77.5946),
    ("APAC", "India", "IN", "INR", "Maharashtra", "Mumbai", 19.0760, 72.8777),
    ("APAC", "India", "IN", "INR", "Delhi", "New Delhi", 28.6139, 77.2090),
    ("APAC", "Australia", "AU", "AUD", "New South Wales", "Sydney", -33.8688, 151.2093),
    ("APAC", "Australia", "AU", "AUD", "Victoria", "Melbourne", -37.8136, 144.9631),
    ("APAC", "Singapore", "SG", "SGD", "Singapore", "Singapore", 1.3521, 103.8198),
    ("APAC", "South Korea", "KR", "KRW", "Seoul", "Seoul", 37.5665, 126.9780),

    # ---- LATAM ----
    ("LATAM", "Brazil", "BR", "BRL", "Sao Paulo", "Sao Paulo", -23.5505, -46.6333),
    ("LATAM", "Brazil", "BR", "BRL", "Rio de Janeiro", "Rio de Janeiro", -22.9068, -43.1729),
    ("LATAM", "Mexico", "MX", "MXN", "Mexico City", "Mexico City", 19.4326, -99.1332),
    ("LATAM", "Mexico", "MX", "MXN", "Jalisco", "Guadalajara", 20.6597, -103.3496),
    ("LATAM", "Argentina", "AR", "ARS", "Buenos Aires", "Buenos Aires", -34.6037, -58.3816),
    ("LATAM", "Chile", "CL", "CLP", "Santiago", "Santiago", -33.4489, -70.6693),
    ("LATAM", "Colombia", "CO", "COP", "Bogota", "Bogota", 4.7110, -74.0721),
]

COLUMNS = ["region", "country", "country_code", "currency_code",
           "state", "city", "latitude", "longitude"]

# Sub-region market groupings, used for the market/territory levels.
MARKETS = {
    "United States": "US Commercial", "Canada": "Canada",
    "Germany": "DACH", "Switzerland": "DACH",
    "United Kingdom": "UK & Ireland",
    "France": "Southern Europe", "Spain": "Southern Europe", "Italy": "Southern Europe",
    "Netherlands": "Benelux & Nordics", "Sweden": "Benelux & Nordics",
    "Poland": "Central Europe",
    "Japan": "Japan", "South Korea": "Japan",
    "China": "Greater China",
    "India": "India & South Asia",
    "Australia": "ANZ", "Singapore": "ASEAN",
    "Brazil": "Brazil", "Mexico": "Mexico & CA",
    "Argentina": "Southern Cone", "Chile": "Southern Cone", "Colombia": "Andean",
}

# Base FX rate to USD (units of local currency per 1 USD) at the start of history.
BASE_FX = {
    "USD": 1.00, "EUR": 0.92, "GBP": 0.79, "CAD": 1.36, "JPY": 149.0,
    "CNY": 7.24, "INR": 83.2, "AUD": 1.52, "SGD": 1.34, "KRW": 1330.0,
    "BRL": 4.97, "MXN": 17.1, "ARS": 880.0, "CLP": 940.0, "COP": 3900.0,
}

CURRENCY_NAMES = {
    "USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound",
    "CAD": "Canadian Dollar", "JPY": "Japanese Yen", "CNY": "Chinese Yuan",
    "INR": "Indian Rupee", "AUD": "Australian Dollar", "SGD": "Singapore Dollar",
    "KRW": "South Korean Won", "BRL": "Brazilian Real", "MXN": "Mexican Peso",
    "ARS": "Argentine Peso", "CLP": "Chilean Peso", "COP": "Colombian Peso",
}
