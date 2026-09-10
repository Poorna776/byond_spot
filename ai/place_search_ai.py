import json
import os

from dotenv import load_dotenv
from google import genai


# =========================================================
# LOAD GEMINI
# =========================================================

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY was not found in the environment."
    )

client = genai.Client(
    api_key=api_key
)


# =========================================================
# CLEAN GEMINI JSON
# =========================================================

def clean_json_response(text):
    """
    Remove Markdown code fences if Gemini adds them.
    """

    if not text:
        return ""

    text = text.strip()

    if text.startswith("```"):

        lines = text.splitlines()

        cleaned_lines = []

        for line in lines:

            if line.strip().startswith("```"):
                continue

            cleaned_lines.append(line)

        text = "\n".join(
            cleaned_lines
        ).strip()

    return text


# =========================================================
# INTERPRET PLACE QUERY
# =========================================================

def interpret_place_query(query):
    """
    Interpret a tourism search query without using Gemini.

    Location extraction is handled by Nominatim later.

    This function exists to preserve compatibility
    with the existing app structure.
    """

    if not query:
        return {
            "location": "",
            "category": "all"
        }

    query_lower = query.lower()

    category = "all"

    category_keywords = {

        "history": [
            "history",
            "historical",
            "historic",
            "heritage",
            "fort",
            "palace",
            "monument",
            "ancient"
        ],

        "nature": [
            "nature",
            "natural",
            "waterfall",
            "forest",
            "lake",
            "hill",
            "hills",
            "park",
            "wildlife",
            "viewpoint"
        ],

        "culture": [
            "culture",
            "cultural",
            "museum",
            "art",
            "arts",
            "theatre",
            "gallery"
        ],

        "spiritual": [
            "spiritual",
            "temple",
            "temples",
            "church",
            "churches",
            "mosque",
            "mosques",
            "shrine",
            "shrines",
            "pilgrimage"
        ],

        "adventure": [
            "adventure",
            "trek",
            "trekking",
            "camping",
            "climbing",
            "hiking",
            "rafting"
        ]
    }

    for category_name, keywords in category_keywords.items():

        if any(
            keyword in query_lower
            for keyword in keywords
        ):
            category = category_name
            break

    result = {
        "location": query,
        "category": category
    }

    print(
        "Place Search Interpretation:",
        result
    )

    return result


# =========================================================
# RANK + CATEGORIZE REAL PLACES
# =========================================================

def rank_places(query, places):
    """
    Rank and categorize real places discovered from OSM.

    Gemini can ONLY work with places supplied by OSM.

    Gemini returns:
        - ranking
        - BYOND Spot category

    Gemini cannot invent:
        - place names
        - coordinates
        - locations
    """

    if not places:

        print(
            "No OSM places available for ranking."
        )

        return []


    # -----------------------------------------------------
    # Fallback
    # -----------------------------------------------------

    fallback_places = places[:12]


    # -----------------------------------------------------
    # Prepare compact data for Gemini
    # -----------------------------------------------------

    simplified_places = []

    for index, place in enumerate(places):

        simplified_places.append({

            "id": index,

            "name": place.get(
                "name",
                ""
            ),

            "osm_category": place.get(
                "category",
                ""
            ),

            "distance_km": place.get(
                "distance_km",
                0
            ),

            "location": place.get(
                "location",
                ""
            ),

            "description": place.get(
                "description",
                ""
            )
        })


    # -----------------------------------------------------
    # ONE AI CALL
    # -----------------------------------------------------

    prompt = f"""
You are the tourism recommendation AI for BYOND Spot.

User search:
{query}

The following places were retrieved from OpenStreetMap.

IMPORTANT RULES:

1. These are real places supplied by OpenStreetMap.
2. ONLY use IDs from this list.
3. NEVER invent a place.
4. NEVER modify a place name.
5. NEVER create coordinates.
6. NEVER create a new place.
7. Rank places according to the user's search.
8. Return at most 12 places.
9. Assign exactly ONE BYOND Spot category to every selected place.

Allowed categories:

- history
- nature
- culture
- spiritual
- adventure

Category guidance:

history:
historical sites, forts, monuments, heritage buildings,
palaces, archaeological sites and historic landmarks.

nature:
forests, waterfalls, lakes, hills, viewpoints, parks,
wildlife and natural attractions.

culture:
museums, art galleries, theatres, cultural centres,
traditional cultural attractions and similar places.

spiritual:
temples, churches, mosques, shrines and pilgrimage places.

adventure:
trekking, hiking, camping, climbing, rafting and
other adventure-oriented attractions.

If a place could belong to multiple categories,
choose the category most relevant to the user's search.

Return ONLY valid JSON.

Format:

[
    {{
        "id": 4,
        "category": "history"
    }},
    {{
        "id": 7,
        "category": "nature"
    }}
]

REAL OSM PLACES:

{json.dumps(
    simplified_places,
    ensure_ascii=False
)}
"""


    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )


        text = clean_json_response(
            response.text
        )


        selected_places = json.loads(
            text
        )


        if not isinstance(
            selected_places,
            list
        ):

            print(
                "AI returned an invalid format."
            )

            return fallback_places


        ranked = []

        allowed_categories = {
            "history",
            "nature",
            "culture",
            "spiritual",
            "adventure"
        }


        used_ids = set()


        for item in selected_places:

            if not isinstance(
                item,
                dict
            ):
                continue


            place_id = item.get(
                "id"
            )

            ai_category = item.get(
                "category",
                ""
            ).lower().strip()


            if not isinstance(
                place_id,
                int
            ):
                continue


            if not (
                0 <= place_id < len(places)
            ):
                continue


            if place_id in used_ids:
                continue


            if ai_category not in allowed_categories:

                ai_category = (
                    places[place_id]
                    .get(
                        "category",
                        "culture"
                    )
                )


            place = dict(
                places[place_id]
            )


            place["ai_category"] = (
                ai_category
            )


            ranked.append(
                place
            )


            used_ids.add(
                place_id
            )


            if len(ranked) >= 12:
                break


        # -------------------------------------------------
        # Gemini returned no usable results
        # -------------------------------------------------

        if not ranked:

            print(
                "AI ranking returned no valid places."
            )

            return fallback_places


        print(
            f"AI ranked {len(ranked)} places "
            f"from {len(places)} OSM results."
        )


        return ranked


    except Exception as error:

        print(
            "Place ranking AI error:",
            error
        )

        return fallback_places