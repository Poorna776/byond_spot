import json
import os

from dotenv import load_dotenv
from google import genai


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY was not found in the environment."
    )


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(
    api_key=api_key
)

MODEL_NAME = "gemini-2.5-flash"


# ============================================================
# JSON CLEANER
# ============================================================

def clean_json_response(text):
    """
    Removes common Markdown formatting from Gemini JSON output.
    """

    text = text.strip()

    if text.startswith("```json"):
        text = text[7:]

    elif text.startswith("```"):
        text = text[3:]

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


# ============================================================
# PLACE AI CHAT
# ============================================================

def generate_place_response(
    place_context,
    user_message
):
    """
    Generate an AI response for the selected place.

    The AI receives real context collected by the backend:
    - place information
    - distance
    - travel time
    - weather
    - crowd activity
    - opening status
    - nearby places

    Gemini is responsible only for reasoning and explanation.
    """

    if not isinstance(place_context, dict):
        raise ValueError(
            "place_context must be a dictionary."
        )

    if not user_message or not user_message.strip():
        raise ValueError(
            "user_message is required."
        )

    # --------------------------------------------------------
    # PREPARE CONTEXT
    # --------------------------------------------------------

    context_json = json.dumps(
        place_context,
        ensure_ascii=False,
        indent=2
    )

    # --------------------------------------------------------
    # SYSTEM INSTRUCTIONS
    # --------------------------------------------------------

    system_instruction = """
You are BYOND AI, the travel assistant inside BYOND Spot.

Your job is to help a traveller understand and make decisions
about the currently selected place.

You MUST use the real context supplied by the application.

IMPORTANT RULES:

1. Do not invent live information.

2. Weather, crowd activity, distance, travel time and opening
   status must come from the supplied context.

3. If a piece of information is missing, clearly say that it
   is currently unavailable instead of guessing.

4. Do not invent nearby places.
   Only recommend nearby places included in the supplied context.

5. Crowd activity should be described qualitatively:
   Low, Moderate, Busy or Very Busy.
   Never claim an exact number of people or phones.

6. If the weather is unsuitable, explain how it affects visiting
   the place and suggest a reasonable alternative only when
   the supplied nearby places support it.

7. Consider distance and travel time when giving recommendations.

8. Consider opening status when recommending whether the user
   should visit now.

9. Give practical travel advice rather than generic tourism text.

10. Keep responses concise and natural, like a helpful human
    travel assistant.

11. If the user asks whether they should visit now, consider:
    - current weather
    - crowd activity
    - opening status
    - distance
    - travel time
    - place characteristics

12. If the user asks for alternatives, recommend only places
    present in the supplied nearby_places data.

13. Do not mention internal APIs, Gemini, prompts, backend code,
    databases or implementation details.

14. If the user asks something unrelated to travel or the
    selected place, politely redirect them toward travel-related
    help.

15. Never present uncertain information as a confirmed fact.

The user's selected place context is supplied below.
"""

    # --------------------------------------------------------
    # GEMINI REQUEST
    # --------------------------------------------------------

    prompt = f"""
{system_instruction}

SELECTED PLACE CONTEXT:
{context_json}

TRAVELLER'S QUESTION:
{user_message.strip()}

Respond directly to the traveller.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    if not response or not response.text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return response.text.strip()


# ============================================================
# AUTOMATIC PLACE RECOMMENDATION
# ============================================================

def generate_place_recommendation(place_context):
    """
    Generate the initial BYOND AI recommendation shown when
    the place-details page is opened.
    """

    if not isinstance(place_context, dict):
        raise ValueError(
            "place_context must be a dictionary."
        )

    context_json = json.dumps(
        place_context,
        ensure_ascii=False,
        indent=2
    )

    system_instruction = """
You are BYOND AI, the travel assistant inside BYOND Spot.

Generate a short, useful recommendation for the traveller
about the selected place.

Use ONLY the supplied context.

Consider:
- current weather
- crowd activity
- opening status
- distance
- travel time
- place information
- nearby alternatives, if available

Do not invent information.

Do not claim exact crowd numbers.

If the place is a good option right now, explain why.

If conditions are not ideal, explain why and, if appropriate,
recommend a nearby alternative from the supplied nearby_places.

The response should feel like a helpful travel assistant,
not a generic description of the place.

Keep the response between 2 and 4 short sentences.
"""

    prompt = f"""
{system_instruction}

PLACE CONTEXT:
{context_json}

Give the traveller your recommendation now.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    if not response or not response.text:
        raise RuntimeError(
            "Gemini returned an empty recommendation."
        )

    return response.text.strip()


# ============================================================
# STRUCTURED PLACE ANALYSIS
# ============================================================

def analyze_place(place_context):
    """
    Generate structured information that the frontend can use
    for a richer AI travel guide.

    Returns:
    {
        "recommendation": "...",
        "best_action": "...",
        "reason": "...",
        "tips": [...]
    }
    """

    if not isinstance(place_context, dict):
        raise ValueError(
            "place_context must be a dictionary."
        )

    context_json = json.dumps(
        place_context,
        ensure_ascii=False,
        indent=2
    )

    prompt = f"""
You are BYOND AI, a practical travel decision assistant.

Analyze the selected place using ONLY the supplied real context.

Consider:
- weather
- crowd activity
- opening status
- distance
- travel time
- place information
- nearby alternatives

Never invent missing information.

Return ONLY valid JSON in exactly this structure:

{{
    "recommendation": "short recommendation",
    "best_action": "Visit now / Visit later / Consider alternative",
    "reason": "short explanation",
    "tips": [
        "practical tip 1",
        "practical tip 2",
        "practical tip 3"
    ]
}}

Keep the recommendation practical and concise.

PLACE CONTEXT:
{context_json}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    if not response or not response.text:
        raise RuntimeError(
            "Gemini returned an empty analysis."
        )

    cleaned_response = clean_json_response(
        response.text
    )

    try:
        result = json.loads(
            cleaned_response
        )

    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid JSON returned by Gemini: {error}"
        )

    # --------------------------------------------------------
    # VALIDATE RESPONSE
    # --------------------------------------------------------

    if not isinstance(result, dict):
        raise RuntimeError(
            "AI analysis must be a JSON object."
        )

    result.setdefault(
        "recommendation",
        "Consider the current travel conditions before visiting."
    )

    result.setdefault(
        "best_action",
        "Consider alternative"
    )

    result.setdefault(
        "reason",
        "Current conditions should be checked before travelling."
    )

    result.setdefault(
        "tips",
        []
    )

    if not isinstance(result["tips"], list):
        result["tips"] = []

    return result