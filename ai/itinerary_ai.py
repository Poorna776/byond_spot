import json
import os
from datetime import datetime

from dotenv import load_dotenv
from google import genai


load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY was not found in the environment."
    )


client = genai.Client(
    api_key=api_key
)


def _get_place_field(place, field_name, default=None):
    if isinstance(place, dict):
        return place.get(field_name, default)
    return getattr(place, field_name, default)


def generate_itinerary(trip_data, available_places=None):
    available_places = available_places or []

    places_context = []
    for place in available_places:
        places_context.append({
            "id": _get_place_field(place, "id"),
            "name": _get_place_field(place, "name"),
            "location": _get_place_field(place, "location"),
            "description": _get_place_field(place, "description"),
            "category": _get_place_field(place, "category"),
            "latitude": _get_place_field(place, "latitude"),
            "longitude": _get_place_field(place, "longitude"),
            "rating": _get_place_field(place, "rating", 4.5)
        })

    prompt = f"""
You are the AI travel planner for BYOND Spot (Smart India Hackathon Tourism Application).

Create a practical, personalized travel itinerary using ONLY the real places provided below.

USER TRIP DETAILS:
Destination: {trip_data["destination"]["name"]}
Start date: {trip_data["start_date"]}
End date: {trip_data["end_date"]}
Duration: {trip_data["duration_days"]} days
Travellers: {trip_data["travellers"]}
Total budget: ₹{trip_data["budget"]}
Interests: {", ".join(trip_data["interests"]) if trip_data["interests"] else "Balanced mix"}
Travel style: {trip_data["travel_style"]}
Preferred transport: {trip_data["transport"]}

REAL AVAILABLE PLACES (SOURCE OF TRUTH):
{json.dumps(places_context, indent=2)}

CRITICAL MANDATORY RULES:
1. GEMINI IS NOT THE SOURCE OF TOURISM PLACES. You MUST ONLY select places from the REAL AVAILABLE PLACES list above.
2. NEVER invent, fabricate, or include fictional attractions. If there are 6 available places, use those 6. Do NOT invent a 7th place to fill an itinerary.
3. If there are fewer places than time slots, schedule fewer activities per day with relaxed pacing instead of inventing attractions.
4. Exact names of places in your output MUST match the "name" field from the REAL AVAILABLE PLACES list.
5. Personalize timing and ordering based on user travel style ({trip_data["travel_style"]}), interests, realistic travel sequence, and budget.
6. Return clean structured JSON only.

RETURN EXACTLY THIS STRUCTURE:
{{
    "destination": "{trip_data["destination"]["name"]}",
    "duration_days": {trip_data["duration_days"]},
    "estimated_total_cost": number,
    "days": [
        {{
            "day": 1,
            "date": "YYYY-MM-DD",
            "places": [
                {{
                    "id": "place_id from list or null",
                    "name": "EXACT place name from REAL AVAILABLE PLACES",
                    "time": "09:00 AM - 11:30 AM",
                    "category": "Culture",
                    "description": "Short description of the visit",
                    "estimated_cost": number,
                    "reason": "Why this fits the traveler"
                }}
            ]
        }}
    ]
}}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    text = response.text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "", 1)
        text = text.replace("```", "", 1)
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Gemini returned an invalid itinerary format."
        ) from error


def _normalise_name(value):
    return " ".join(str(value or "").lower().split())


def _find_matching_place(place_name, available_places):
    target = _normalise_name(place_name)
    if not target:
        return None

    for place in available_places:
        name = _normalise_name(_get_place_field(place, "name"))
        if name == target:
            return place

    for place in available_places:
        name = _normalise_name(_get_place_field(place, "name"))
        if target in name or name in target:
            return place

    return None


def enrich_itinerary_with_crowd(itinerary, trip_data, available_places=None, max_venues=6):
    """
    Attach BestTime forecast data to itinerary places and let BYOND AI
    make a small crowd-aware scheduling pass.
    """
    from services.crowd_service import get_forecast_crowd

    available_places = available_places or []
    used = 0

    for day in itinerary.get("days", []):
        date_text = day.get("date")
        if not date_text:
            continue

        try:
            day_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue

        for item in day.get("places", []):
            matched = _find_matching_place(item.get("name"), available_places)
            if not matched or used >= max_venues:
                item["crowd_activity"] = {
                    "available": False,
                    "source": "BestTime",
                    "level": "Unavailable",
                    "message": "Crowd forecast unavailable for this place."
                }
                continue

            start_text = str(item.get("time", "12:00 PM")).split("-")[0].strip()
            target_dt = None
            for fmt in ("%I:%M %p", "%I %p", "%H:%M"):
                try:
                    parsed = datetime.strptime(start_text, fmt).time()
                    target_dt = datetime.combine(day_date, parsed)
                    break
                except ValueError:
                    pass

            if target_dt is None:
                target_dt = datetime.combine(day_date, datetime.min.time()).replace(hour=12)

            crowd = get_forecast_crowd(
                {
                    "name": _get_place_field(matched, "name"),
                    "location": _get_place_field(matched, "location"),
                },
                target_dt,
            )
            item["crowd_activity"] = crowd
            item["crowd_score"] = crowd.get("forecast_busyness")
            item["crowd_level"] = crowd.get("level", "Unavailable")
            used += 1

    # Second pass: optimize order/timing if high crowd detected
    crowd_items = []
    for day in itinerary.get("days", []):
        for item in day.get("places", []):
            crowd = item.get("crowd_activity") or {}
            if crowd.get("available"):
                crowd_items.append({
                    "day": day.get("day"),
                    "date": day.get("date"),
                    "name": item.get("name"),
                    "time": item.get("time"),
                    "crowd_level": crowd.get("level"),
                    "forecast_busyness": crowd.get("forecast_busyness"),
                })

    if not crowd_items:
        return itinerary

    prompt = f"""
You are BYOND AI's crowd-aware itinerary optimizer.

The itinerary below has been generated using real places.
Your ONLY job is to improve the schedule using the supplied BestTime crowd forecasts.

RULES:
1. Never add a new place.
2. Never remove a place.
3. Keep each place on its existing day.
4. You may adjust the time slot of a place to reduce exposure to high crowd periods (Very Busy / Busy).
5. Preserve estimated costs, descriptions, categories, and reasons.
6. Return JSON only using exactly the same itinerary structure.

TRIP:
{json.dumps(trip_data, ensure_ascii=False, indent=2)}

CROWD DATA USED:
{json.dumps(crowd_items, ensure_ascii=False, indent=2)}

CURRENT ITINERARY:
{json.dumps(itinerary, ensure_ascii=False, indent=2)}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "", 1).replace("```", "", 1).strip()
        optimized = json.loads(text)

        old_lookup = {
            (_normalise_name(item.get("name")), day.get("day")): item.get("crowd_activity")
            for day in itinerary.get("days", [])
            for item in day.get("places", [])
        }
        for day in optimized.get("days", []):
            for item in day.get("places", []):
                key = (_normalise_name(item.get("name")), day.get("day"))
                if key in old_lookup:
                    item["crowd_activity"] = old_lookup[key]
                    item["crowd_level"] = (old_lookup[key] or {}).get("level", "Unavailable")
        return optimized
    except Exception as error:
        print("Crowd-aware itinerary optimization skipped:", error)
        return itinerary
