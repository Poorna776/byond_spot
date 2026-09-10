import os
import time
from datetime import datetime
from threading import Lock

import requests
from dotenv import load_dotenv

load_dotenv()

BESTTIME_PRIVATE_KEY = os.getenv("BESTTIME_API_KEY_PRIVATE")
BESTTIME_PUBLIC_KEY = os.getenv("BESTTIME_API_KEY_PUBLIC")

LIVE_URL = "https://besttime.app/api/v1/forecasts/live"
WEEK_RAW2_URL = "https://besttime.app/api/v1/forecasts/week/raw2"

CACHE_TTL_SECONDS = 45 * 60
_FORECAST_CACHE_TTL_SECONDS = 12 * 60 * 60
_cache = {}
_cache_lock = Lock()


def _cache_get(key):
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        if time.time() - item["created"] > item["ttl"]:
            _cache.pop(key, None)
            return None
        return item["value"]


def _cache_set(key, value, ttl):
    with _cache_lock:
        _cache[key] = {
            "created": time.time(),
            "ttl": ttl,
            "value": value,
        }


def _normalise_text(value):
    return " ".join(str(value or "").lower().split())


def _place_name_address(place):
    name = str(place.get("name") or "").strip()
    address = str(
        place.get("location")
        or place.get("address")
        or ""
    ).strip()
    return name, address


def crowd_level(score):
    """Map BestTime's 0-100 relative busyness to a BYOND label."""
    if score is None:
        return "Unavailable"
    score = float(score)
    if score <= 30:
        return "Low"
    if score <= 60:
        return "Moderate"
    if score <= 80:
        return "Busy"
    return "Very Busy"


def _base_unavailable(reason="Crowd data unavailable"):
    return {
        "available": False,
        "source": "BestTime",
        "is_live": False,
        "live_busyness": None,
        "forecast_busyness": None,
        "delta_from_expected": None,
        "level": "Unavailable",
        "trend": "unavailable",
        "message": reason,
    }


def get_live_crowd(place):
    """
    Get current BestTime live foot traffic for a venue.

    BestTime's live endpoint returns current busyness relative to
    that venue's weekly peak plus the expected busyness for the
    same hour. The result is cached briefly so page refreshes do
    not repeatedly consume credits.
    """
    if not BESTTIME_PRIVATE_KEY:
        return _base_unavailable("BestTime private API key is not configured")

    name, address = _place_name_address(place)
    if not name:
        return _base_unavailable("Venue name is unavailable")

    cache_key = f"live:{_normalise_text(name)}|{_normalise_text(address)}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "api_key_private": BESTTIME_PRIVATE_KEY,
        "venue_name": name,
        "venue_address": address or name,
    }

    try:
        print(f"Fetching live crowd data for: {name}")
        response = requests.post(
            LIVE_URL,
            params=params,
            timeout=25,
        )
        print(f"BestTime response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        analysis = data.get("analysis") or {}
        live = analysis.get("venue_live_busyness")
        forecast = analysis.get("venue_forecasted_busyness")
        delta = analysis.get("venue_live_forecasted_delta")

        if str(data.get("status", "")).lower() != "ok":
            # If live foot traffic sensor data is not available, but expected forecast is provided
            if forecast is not None:
                result = {
                    "available": True,
                    "source": "BestTime",
                    "is_live": False,
                    "live_busyness": None,
                    "forecast_busyness": forecast,
                    "delta_from_expected": None,
                    "level": crowd_level(forecast),
                    "trend": "forecast",
                    "local_time": (
                        (data.get("venue_info") or {}).get("venue_current_localtime")
                    ),
                    "hour_start": analysis.get("hour_start"),
                    "hour_end": analysis.get("hour_end"),
                    "message": "Expected crowd forecast available",
                }
                print(f"Crowd data available: True (expected forecast)")
                _cache_set(cache_key, result, CACHE_TTL_SECONDS)
                return result

            raw_msg = str(data.get("message") or "")
            clean_msg = "Crowd data unavailable" if "venue not found" in raw_msg.lower() else (raw_msg or "Crowd data unavailable")
            result = _base_unavailable(clean_msg)
            print(f"Crowd data available: False ({clean_msg})")
            _cache_set(cache_key, result, CACHE_TTL_SECONDS)
            return result

        is_live = live is not None
        score = live if is_live else forecast
        available = score is not None

        result = {
            "available": available,
            "source": "BestTime",
            "is_live": is_live,
            "live_busyness": live,
            "forecast_busyness": forecast,
            "delta_from_expected": delta,
            "level": crowd_level(score),
            "trend": (
                "busier_than_expected" if delta is not None and delta > 5
                else "quieter_than_expected" if delta is not None and delta < -5
                else "around_expected" if delta is not None
                else "forecast" if not is_live
                else "unknown"
            ),
            "local_time": (
                (data.get("venue_info") or {}).get("venue_current_localtime")
            ),
            "hour_start": analysis.get("hour_start"),
            "hour_end": analysis.get("hour_end"),
        }

        print(f"Crowd data available: {result['available']}")
        _cache_set(cache_key, result, CACHE_TTL_SECONDS)
        return result

    except requests.RequestException as error:
        print("BestTime live crowd error:", error)
        result = _base_unavailable("Crowd activity temporarily unavailable")
        print("Crowd data available: False (temporarily unavailable)")
        _cache_set(cache_key, result, 5 * 60)
        return result
    except (ValueError, TypeError) as error:
        print("BestTime response parsing error:", error)
        result = _base_unavailable("Crowd activity temporarily unavailable")
        print("Crowd data available: False (parsing error)")
        _cache_set(cache_key, result, 5 * 60)
        return result


def _forecast_value_for_datetime(week_raw, target_datetime):
    """
    Extract the expected relative busyness for a requested local
    date/time from BestTime's week_raw2 format.

    BestTime splits each day from 6 AM through 5 AM the next day.
    """
    weekday = target_datetime.weekday()
    hour = target_datetime.hour

    day_entry = next(
        (
            item for item in week_raw
            if int(item.get("day_int", -1)) == weekday
        ),
        None,
    )

    if not day_entry:
        return None

    values = day_entry.get("day_raw") or []
    if not values:
        return None

    # raw2 starts at 06:00.  00:00-05:00 belong at the end.
    index = hour - 6 if hour >= 6 else hour + 18
    if index < 0 or index >= len(values):
        return None

    return values[index]


def get_forecast_crowd(place, target_datetime):
    """
    Get expected busyness for a future/current trip date and time.

    A fresh forecast is requested only when needed and then cached.
    This is intentionally used for a small number of itinerary
    places, not for every OSM result.
    """
    if not BESTTIME_PRIVATE_KEY:
        return _base_unavailable("BestTime private API key is not configured")

    name, address = _place_name_address(place)
    if not name:
        return _base_unavailable("Venue name is unavailable")

    cache_key = f"forecast:{_normalise_text(name)}|{_normalise_text(address)}"
    cached = _cache_get(cache_key)

    if cached is None:
        params = {
            "api_key_private": BESTTIME_PRIVATE_KEY,
            "venue_name": name,
            "venue_address": address or name,
        }

        try:
            print(f"Fetching forecast crowd data for: {name} (target: {target_datetime.strftime('%Y-%m-%d %H:%M')})")
            response = requests.post(
                WEEK_RAW2_URL,
                params=params,
                timeout=25,
            )
            print(f"BestTime forecast response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()

            if str(data.get("status", "")).lower() != "ok":
                raw_msg = str(data.get("message") or "")
                clean_msg = "Crowd data unavailable" if "venue not found" in raw_msg.lower() else (raw_msg or "Crowd data unavailable")
                print(f"Crowd data available: False ({clean_msg})")
                return _base_unavailable(clean_msg)

            week_raw = (data.get("analysis") or {}).get("week_raw") or []
            cached = {
                "week_raw": week_raw,
                "venue_name": data.get("venue_name") or name,
                "forecast_updated_on": data.get("forecast_updated_on"),
            }
            _cache_set(cache_key, cached, _FORECAST_CACHE_TTL_SECONDS)

        except requests.RequestException as error:
            print("BestTime forecast error:", error)
            print("Crowd data available: False (temporarily unavailable)")
            return _base_unavailable("Crowd activity temporarily unavailable")
        except (ValueError, TypeError) as error:
            print("BestTime forecast parsing error:", error)
            print("Crowd data available: False (parsing error)")
            return _base_unavailable("Crowd activity temporarily unavailable")

    score = _forecast_value_for_datetime(
        cached.get("week_raw", []),
        target_datetime,
    )

    available = score is not None
    result = {
        "available": available,
        "source": "BestTime",
        "is_live": False,
        "live_busyness": None,
        "forecast_busyness": score,
        "delta_from_expected": None,
        "level": crowd_level(score),
        "trend": "forecast",
        "forecast_for": target_datetime.strftime("%Y-%m-%d %H:%M"),
        "forecast_updated_on": cached.get("forecast_updated_on"),
        "message": "Forecast available" if available else "Crowd data unavailable"
    }
    print(f"Crowd data available: {result['available']}")
    return result
