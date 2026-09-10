import json
import os

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


def generate_trip_suggestions(
    trip_context,
    available_places=None
):

    available_places = available_places or []

    places_context = []

    for place in available_places:

        places_context.append({

            "id": place.id,

            "name": place.name,

            "location": place.location,

            "description": place.description,

            "category": place.category,

            "latitude": place.latitude,

            "longitude": place.longitude,

            "rating": place.rating

        })


    prompt = f"""
You are BYOND AI, the live travel companion for BYOND Spot.

Your job is to analyze the traveler's CURRENT trip situation
and provide useful, practical recommendations.

Do NOT automatically modify the traveler's itinerary.

Your recommendations are advisory only.

==================================================
CURRENT TRIP CONTEXT
==================================================

Trip ID:
{trip_context.get("trip_id")}

Current Day:
{trip_context.get("current_day")}

Current Time:
{trip_context.get("current_time")}

Current Location:
{json.dumps(
    trip_context.get("current_location"),
    indent=2
)}

Travellers:
{trip_context.get("travellers", 1)}

Remaining Budget:
₹{trip_context.get("remaining_budget", 0)}

Today's Spending:
₹{trip_context.get("today_spent", 0)}

Total Spending:
₹{trip_context.get("total_spent", 0)}

Remaining Days:
{trip_context.get("remaining_days", 0)}

User Interests:
{json.dumps(
    trip_context.get("user_interests", []),
    indent=2
)}

Weather:
{json.dumps(
    trip_context.get("weather", {}),
    indent=2
)}

Crowd Activity:
{json.dumps(
    trip_context.get("crowd_activity", []),
    indent=2
)}

Today's Itinerary:
{json.dumps(
    trip_context.get("today_itinerary", []),
    indent=2
)}

Full Current Itinerary:
{json.dumps(
    trip_context.get("current_itinerary", []),
    indent=2
)}

Completed Places:
{json.dumps(
    trip_context.get("completed_places", []),
    indent=2
)}

Skipped Places:
{json.dumps(
    trip_context.get("skipped_places", []),
    indent=2
)}

==================================================
KNOWN BYOND SPOT PLACES
==================================================

{json.dumps(
    places_context,
    indent=2
)}

==================================================
HOW YOU SHOULD REASON
==================================================

Consider the following when making recommendations:

1. Current location.

2. Current time.

3. Current day of the trip.

4. Remaining itinerary.

5. Places already completed.

6. Places skipped by the traveler.

7. Weather conditions.

8. Crowd activity, especially whether a planned place is currently Very Busy, Busy, Moderate or Low.

9. Remaining budget.

10. Today's spending.

11. Traveler interests.

12. Number of travellers.

13. Practical travel timing.

14. Nearby experiences.

15. Whether an activity is suitable for the current conditions.

Examples:

- If the current planned destination has High/Very Busy crowd activity,
  explain the impact and recommend delaying it or choosing a less crowded
  supplied alternative when that is practical.

- If crowd data is marked as live, treat it as current activity. If it is
  a forecast, treat it as expected activity for the planned time.

- Never convert a BestTime busyness percentage into an exact number of people.

- If rain probability is high and an outdoor activity is planned,
  recommend an indoor or weather-friendly experience.

- If the traveler is spending more than expected,
  recommend lower-cost alternatives.

- If the traveler is close to a known place that matches their
  interests, recommend it.

- If the traveler has already completed a place, do not recommend
  it again.

- If a place was skipped, do not immediately recommend it again
  unless there is a strong contextual reason.

- If there are no meaningful changes needed, say that the trip
  is currently on track.

==================================================
IMPORTANT SAFETY / ACCURACY RULES
==================================================

1. Do not invent specific real-world places.

2. Prefer places from the provided BYOND Spot places list.

3. Do not claim that crowd information is live unless the
   supplied crowd data says it is live.

4. Do not claim weather information is live unless the supplied
   weather data says it is live.

5. Do not automatically change the itinerary.

6. Recommendations should be concise and practical.

7. Never recommend a place that already appears in completed_places.

8. Never recommend a place simply because it exists in the
   database. It must be contextually useful.

9. Return JSON only.

==================================================
RETURN EXACTLY THIS STRUCTURE
==================================================

{{
    "suggestions": [
        {{
            "type": "Weather | Crowd | Nearby | Budget | Explore",
            "title": "Short recommendation title",
            "text": "Useful recommendation for the traveler",
            "why": "Explain why BYOND AI is making this recommendation",
            "place_id": null
        }}
    ]
}}

Return at most 4 suggestions.

If a recommendation refers to a known BYOND Spot place,
use its database ID as place_id.

If the recommendation is general advice,
use null for place_id.
"""


    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )


    text = response.text.strip()


    if text.startswith("```"):

        text = text.replace(
            "```json",
            "",
            1
        )

        text = text.replace(
            "```",
            "",
            1
        )

        text = text.strip()


    try:

        result = json.loads(text)

    except json.JSONDecodeError as error:

        raise ValueError(
            "Gemini returned invalid trip suggestion JSON."
        ) from error


    if not isinstance(result, dict):

        raise ValueError(
            "Gemini returned an invalid response."
        )


    suggestions = result.get(
        "suggestions",
        []
    )


    if not isinstance(
        suggestions,
        list
    ):

        raise ValueError(
            "Invalid suggestions format."
        )


    return {
        "suggestions": suggestions[:4]
    }