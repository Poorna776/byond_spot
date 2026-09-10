import requests
import time
from threading import Lock

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_CACHE_TTL = 15 * 60  # 15 minutes
_weather_cache = {}
_cache_lock = Lock()


def weather_code_to_text(code):
    """Convert Open-Meteo WMO weather codes into human-readable conditions."""
    if code is None:
        return "Weather unavailable"
    if code == 0:
        return "Clear sky"
    if code in [1, 2, 3]:
        return "Partly cloudy"
    if code in [45, 48]:
        return "Foggy"
    if code in [51, 53, 55, 56, 57]:
        return "Drizzle"
    if code in [61, 63, 65, 66, 67]:
        return "Rainy"
    if code in [71, 73, 75, 77]:
        return "Snowy"
    if code in [80, 81, 82]:
        return "Rain showers"
    if code in [85, 86]:
        return "Snow showers"
    if code in [95, 96, 99]:
        return "Thunderstorm"
    return "Pleasant"


def get_weather(latitude, longitude):
    """
    Get current weather for a coordinate using Open-Meteo.
    Caches result for 15 minutes to reduce external calls.
    """
    if latitude is None or longitude is None:
        return {
            "temperature": None,
            "feels_like": None,
            "precipitation": None,
            "rain": None,
            "wind_speed": None,
            "condition": "Weather unavailable",
            "available": False
        }

    try:
        lat = round(float(latitude), 3)
        lng = round(float(longitude), 3)
    except (ValueError, TypeError):
        return {
            "temperature": None,
            "feels_like": None,
            "precipitation": None,
            "rain": None,
            "wind_speed": None,
            "condition": "Weather unavailable",
            "available": False
        }

    cache_key = f"{lat}:{lng}"
    with _cache_lock:
        if cache_key in _weather_cache:
            entry = _weather_cache[cache_key]
            if time.time() - entry["time"] < WEATHER_CACHE_TTL:
                return entry["data"]

    try:
        response = requests.get(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lng,
                "current": (
                    "temperature_2m,"
                    "apparent_temperature,"
                    "precipitation,"
                    "rain,"
                    "weather_code,"
                    "wind_speed_10m"
                ),
                "timezone": "auto"
            },
            timeout=8
        )
        response.raise_for_status()
        data = response.json()
        current = data.get("current", {})

        result = {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "precipitation": current.get("precipitation"),
            "rain": current.get("rain"),
            "wind_speed": current.get("wind_speed_10m"),
            "condition": weather_code_to_text(current.get("weather_code")),
            "available": current.get("temperature_2m") is not None
        }

        with _cache_lock:
            _weather_cache[cache_key] = {
                "time": time.time(),
                "data": result
            }
        return result

    except Exception as error:
        print(f"Weather service error for ({latitude}, {longitude}):", error)
        return {
            "temperature": None,
            "feels_like": None,
            "precipitation": None,
            "rain": None,
            "wind_speed": None,
            "condition": "Weather unavailable",
            "available": False
        }
