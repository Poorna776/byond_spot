import requests
from datetime import datetime

from services.osm_service import (
    calculate_distance,
    discover_places
)
from services.crowd_service import get_live_crowd
from services.weather_service import get_weather


# =========================================================
# OPENING STATUS
# =========================================================

def get_opening_status(opening_hours):
    """
    Provide a simple opening-hours interpretation.
    """
    if not opening_hours:
        return {
            "available": False,
            "status": "Opening hours unavailable",
            "raw": None
        }

    return {
        "available": True,
        "status": "Opening hours available",
        "raw": opening_hours
    }


# =========================================================
# CROWD ACTIVITY
# =========================================================

def get_crowd_activity(place):
    """Get current crowd activity from BestTime."""
    try:
        return get_live_crowd(place)
    except Exception as error:
        print("Crowd activity lookup error:", error)
        return {
            "available": False,
            "level": "Unavailable",
            "message": "Crowd data unavailable"
        }


# =========================================================
# NEARBY PLACES
# =========================================================

def get_nearby_places(
    latitude,
    longitude,
    current_place_id=None,
    radius=50000
):
    """
    Discover real nearby places.
    Prioritizes SQLite database places, computing distance and sorting.
    The selected place itself is excluded.
    """
    nearby = []
    seen_names = set()

    # 1. First, check all other SQLite database places
    try:
        from database import Place
        db_places = Place.query.all()
        for p in db_places:
            pid = f"db_{p.id}"
            if current_place_id and (str(current_place_id) == pid or str(current_place_id) == str(p.id)):
                continue
            dist = None
            if p.latitude is not None and p.longitude is not None and latitude is not None and longitude is not None:
                dist = round(calculate_distance(latitude, longitude, p.latitude, p.longitude), 1)
            
            seen_names.add(p.name.lower().strip())
            nearby.append({
                "id": pid,
                "name": p.name,
                "location": p.location,
                "category": p.category,
                "distance_km": dist,
                "description": p.description,
                "source": "database"
            })
    except Exception as db_err:
        print("Nearby database lookup error:", db_err)

    # Sort database places by distance
    nearby.sort(key=lambda x: (x.get("distance_km") if x.get("distance_km") is not None else 999))

    # If we already have database places, return them immediately without calling Overpass
    if nearby:
        return nearby[:5]

    # 2. Only if no database places exist, try fast OSM discovery
    if latitude is not None and longitude is not None:
        try:
            places = discover_places(
                latitude=latitude,
                longitude=longitude,
                radius=min(radius, 8000)
            )
            for place in places:
                osm_id = place.get("osm_id") or place.get("id")
                name = place.get("name", "").strip()
                if not name or name.lower() in seen_names:
                    continue
                if current_place_id and (str(osm_id) == str(current_place_id)):
                    continue
                seen_names.add(name.lower())
                nearby.append({
                    "id": osm_id,
                    "name": name,
                    "location": place.get("location"),
                    "category": place.get("category"),
                    "distance_km": place.get("distance_km"),
                    "description": place.get("description"),
                    "source": "osm"
                })
        except Exception as error:
            print("Nearby OSM discovery skipped:", error)

    nearby.sort(key=lambda x: (x.get("distance_km") if x.get("distance_km") is not None else 999))
    return nearby[:5]


# =========================================================
# PLACE CONTEXT
# =========================================================

def build_place_context(
    place,
    user_latitude=None,
    user_longitude=None
):
    """
    Build one structured context object for the
    Place AI system.

    Gemini receives this context and reasons over
    the supplied facts instead of inventing them.
    """
    if not place:
        return None

    place_id = place.get("id") or place.get("osm_id")
    place_latitude = place.get("latitude")
    place_longitude = place.get("longitude")

    # Distance from user to place
    distance_km = place.get("distance_km")
    if (
        distance_km is None
        and user_latitude is not None
        and user_longitude is not None
        and place_latitude is not None
        and place_longitude is not None
    ):
        try:
            distance_km = round(calculate_distance(
                user_latitude,
                user_longitude,
                place_latitude,
                place_longitude
            ), 2)
        except Exception:
            distance_km = None

    # Weather at destination
    weather = None
    if place_latitude is not None and place_longitude is not None:
        weather = get_weather(place_latitude, place_longitude)

    # Live or forecast crowd
    crowd = get_crowd_activity(place)

    # Opening hours
    opening_status = get_opening_status(place.get("opening_hours"))

    # Current local time
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Nearby real places (around the DESTINATION, not far away from user)
    nearby_places = []
    if place_latitude is not None and place_longitude is not None:
        nearby_places = get_nearby_places(
            latitude=place_latitude,
            longitude=place_longitude,
            current_place_id=place_id
        )

    return {
        "place": {
            "id": place_id,
            "name": place.get("name"),
            "location": place.get("location"),
            "category": place.get("category"),
            "description": place.get("description"),
            "latitude": place_latitude,
            "longitude": place_longitude,
            "website": place.get("website"),
            "rating": place.get("rating"),
            "source": place.get("source", "database")
        },
        "user": {
            "latitude": user_latitude,
            "longitude": user_longitude,
            "distance_km": distance_km
        },
        "weather": weather,
        "crowd_activity": crowd,
        "opening_hours": opening_status,
        "current_time": current_time,
        "nearby_places": nearby_places
    }