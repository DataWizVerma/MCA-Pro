"""
fetchOriginal.py
----------------
Project : Digital Image Forensics System for Tampering Detection
College : Chandigarh University
Author  : Kumar Verma
Purpose : Extract GPS / datetime metadata from image EXIF data and query the
          Open-Meteo historical weather API to validate weather depicted in the
          image against actual recorded conditions.
"""

import json
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from exif import Image as ExifImage
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError


# ---------------------------------------------------------------------------
# WMO Weather Interpretation Codes  (complete mapping — ISO 4677)
# Reference: https://open-meteo.com/en/docs
# ---------------------------------------------------------------------------
WEATHER_CODE_MAP = {
    0:  "Sunny / Clear Sky",
    1:  "Mainly Clear",
    2:  "Partly Cloudy",
    3:  "Overcast",
    45: "Foggy",
    48: "Rime Fog (Depositing)",
    51: "Light Drizzle",
    53: "Moderate Drizzle",
    55: "Dense Drizzle",
    56: "Light Freezing Drizzle",
    57: "Heavy Freezing Drizzle",
    61: "Slight Rain",
    63: "Moderate Rain",
    65: "Heavy Rain",
    66: "Light Freezing Rain",
    67: "Heavy Freezing Rain",
    71: "Slight Snowfall",
    73: "Moderate Snowfall",
    75: "Heavy Snowfall",
    77: "Snow Grains",
    80: "Slight Rain Showers",
    81: "Moderate Rain Showers",
    82: "Violent Rain Showers",
    85: "Slight Snow Showers",
    86: "Heavy Snow Showers",
    95: "Thunderstorm (Slight/Moderate)",
    96: "Thunderstorm with Slight Hail",
    99: "Thunderstorm with Heavy Hail",
}

# Map Open-Meteo weather codes to the 4 Weather-CNN class labels
CNN_CLASS_MAP = {
    0:  "Sunny",
    1:  "Sunny",
    2:  "Sunny",
    3:  "Rainy",            # overcast → rainy-like
    45: "Rainy",
    48: "Rainy",
    51: "Rainy",
    53: "Rainy",
    55: "Rainy",
    56: "Rainy",
    57: "Rainy",
    61: "Rainy",
    63: "Rainy",
    65: "Rainy",
    66: "Rainy",
    67: "Rainy",
    71: "Snow",
    73: "Snow",
    75: "Snow",
    77: "Snow",
    80: "Rainy",
    81: "Rainy",
    82: "Rainy",
    85: "Snow",
    86: "Snow",
    95: "Lightning",
    96: "Lightning",
    99: "Lightning",
}

# Open-Meteo historical ERA5 re-analysis base URL
BASE_URL = "https://archive-api.open-meteo.com/v1/era5?"


# ---------------------------------------------------------------------------
# Helper: convert DMS (degrees, minutes, seconds) GPS tuple to decimal degrees
# ---------------------------------------------------------------------------
def _decimal_coords(coords: tuple, ref: str) -> float:
    """
    Convert GPS coordinates from DMS format (as stored in EXIF) to a signed
    decimal degrees float.

    Parameters
    ----------
    coords : tuple – (degrees, minutes, seconds) as floats.
    ref    : str   – 'N', 'S', 'E', or 'W'.

    Returns
    -------
    float – signed decimal degrees (negative for South / West).
    """
    decimal = coords[0] + coords[1] / 60.0 + coords[2] / 3600.0
    if ref in ("S", "W"):
        decimal = -decimal
    return round(decimal, 6)


# ---------------------------------------------------------------------------
# 1. Extract GPS coordinates and datetime from EXIF
# ---------------------------------------------------------------------------
def image_coordinates(image_path: str):
    """
    Parse the EXIF metadata of a JPEG image to extract:
    - GPS latitude and longitude
    - Date and time the photograph was taken

    Parameters
    ----------
    image_path : str – path to the JPEG image.

    Returns
    -------
    (date_time, latitude, longitude, outdoor) : tuple
        date_time : str  – 'YYYY:MM:DD HH:MM:SS' or None
        latitude  : float or None
        longitude : float or None
        outdoor   : bool – True only when both GPS and datetime are available.
    """
    outdoor = True

    try:
        with open(image_path, "rb") as f:
            img = ExifImage(f)
    except Exception:
        return None, None, None, False

    if not img.has_exif:
        # Image was not taken with a camera, or EXIF was stripped
        return None, None, None, False

    # ---- Extract GPS coordinates ----------------------------------------
    try:
        lat = _decimal_coords(img.gps_latitude,  img.gps_latitude_ref)
        lon = _decimal_coords(img.gps_longitude, img.gps_longitude_ref)
    except AttributeError:
        # GPS tags are absent — device did not record location
        return None, None, None, False

    # ---- Extract date/time of capture -----------------------------------
    try:
        date_time = img.datetime_original        # preferred tag
    except AttributeError:
        try:
            date_time = img.gps_datestamp + " 12:00:00"   # fallback GPS date
        except AttributeError:
            # No date information at all
            return None, None, None, False

    return date_time, lat, lon, outdoor


# ---------------------------------------------------------------------------
# 2. Query historical weather API
# ---------------------------------------------------------------------------
def get_weather(date_time: str, lat: float, lon: float):
    """
    Query the Open-Meteo ERA5 historical weather API for the weather conditions
    at the given location and time.

    Parameters
    ----------
    date_time : str   – 'YYYY:MM:DD HH:MM:SS' (EXIF format).
    lat       : float – decimal degrees latitude.
    lon       : float – decimal degrees longitude.

    Returns
    -------
    (location_name, date_str, weather_description, cnn_class) : tuple
        location_name    : str – human-readable city/country from reverse geocoding.
        date_str         : str – 'YYYY-MM-DD'.
        weather_description : str – full WMO weather description or 'NA'.
        cnn_class        : str – mapped CNN class label (Sunny/Rainy/Snow/Lightning).
    """
    # Convert EXIF date format 'YYYY:MM:DD' → 'YYYY-MM-DD'
    date_str = date_time[:10].replace(":", "-")
    time_str = date_time[11:]
    hour     = int(time_str[:2])

    # ---- Reverse geocode to get location name ---------------------------
    location_name = "Unknown Location"
    try:
        geolocator = Nominatim(user_agent="image_forensics_chandigarh_university")
        loc = geolocator.reverse(f"{lat},{lon}", timeout=10)
        if loc:
            location_name = loc.address
    except (GeocoderTimedOut, GeocoderServiceError):
        location_name = f"({lat:.4f}, {lon:.4f})"

    # ---- Fetch historical weather data ----------------------------------
    url = (
        f"{BASE_URL}"
        f"latitude={lat}&longitude={lon}"
        f"&start_date={date_str}&end_date={date_str}"
        f"&hourly=weathercode&timezone=auto"
    )

    try:
        response  = urlopen(url, timeout=15)
        data_json = json.loads(response.read())
        weather_codes = data_json["hourly"]["weathercode"]

        # Use the weather code for the hour the photo was taken
        # Open-Meteo returns 24 hourly values (index 0–23)
        idx = max(0, min(hour, 23))
        code = weather_codes[idx]

        if code is None:
            return location_name, date_str, "NA", "NA"

        weather_desc = WEATHER_CODE_MAP.get(code, f"Weather code {code}")
        cnn_class    = CNN_CLASS_MAP.get(code, "Sunny")

    except (URLError, HTTPError, KeyError, json.JSONDecodeError):
        return location_name, date_str, "NA", "NA"

    return location_name, date_str, weather_desc, cnn_class


# ---------------------------------------------------------------------------
# 3. Get full structured EXIF report (for the forensic report)
# ---------------------------------------------------------------------------
def get_full_exif_report(image_path: str) -> dict:
    """
    Return a structured summary of all available EXIF metadata.

    Parameters
    ----------
    image_path : str – path to the image file.

    Returns
    -------
    report : dict – categorised EXIF information.
    """
    report = {
        "has_exif":   False,
        "camera":     {},
        "capture":    {},
        "gps":        {},
        "software":   {},
    }

    try:
        with open(image_path, "rb") as f:
            img = ExifImage(f)

        if not img.has_exif:
            return report

        report["has_exif"] = True

        # Camera info
        for attr in ("make", "model", "lens_make", "lens_model", "body_serial_number"):
            try:
                val = getattr(img, attr)
                report["camera"][attr] = val
            except AttributeError:
                pass

        # Capture settings
        for attr in ("datetime_original", "exposure_time", "f_number",
                     "photographic_sensitivity", "focal_length", "flash",
                     "white_balance", "metering_mode"):
            try:
                val = getattr(img, attr)
                report["capture"][attr] = val
            except AttributeError:
                pass

        # GPS info
        try:
            lat = _decimal_coords(img.gps_latitude, img.gps_latitude_ref)
            lon = _decimal_coords(img.gps_longitude, img.gps_longitude_ref)
            report["gps"]["latitude"]  = lat
            report["gps"]["longitude"] = lon
        except AttributeError:
            pass

        # Software / editing history (tampered images often show Photoshop here)
        for attr in ("software", "processing_software", "artist", "copyright"):
            try:
                val = getattr(img, attr)
                report["software"][attr] = val
            except AttributeError:
                pass

    except Exception:
        pass

    return report
