"""Constants for Toyota Connected Europe API (from HAR)."""

# Base URLs
API_BASE_URL = "https://ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io"
AUTH_BASE_URL = "https://b2c-login.toyota-europe.com"

# OAuth2 / ForgeRock
OAUTH_REALM_PATH = "/oauth2/realms/root/realms/tme"
JSON_REALM_PATH = "/json/realms/root/realms/tme"
CLIENT_ID = "oneapp"
CLIENT_SECRET = "oneapp"
REDIRECT_URI = "com.toyota.oneapp:/oauth2Callback"
AUTH_INDEX_SERVICE = "oneapp"
SCOPE = "openid profile write"
TOKEN_EXPIRY_BUFFER_SECONDS = 300  # refresh 5 min before expiry

# API key (public, from app)
API_KEY = "tTZipv6liF74PwMfk9Ed68AQ0bISswwf3iHQdqcF"

# Default app headers (Toyota OneAPI expects these)
DEFAULT_REGION = "EU"
DEFAULT_BRAND = "T"
DEFAULT_APP_VERSION = "2.20.0"
DEFAULT_CHANNEL = "ONEAPP"
