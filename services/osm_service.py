import math
import time
import requests


# =========================================================
# EXTERNAL SERVICES
# =========================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HEADERS = {
    "User-Agent": "BYOND-Spot-SIH-Tourism-App/1.0"
}

# Keep requests reasonably short so one unavailable server
# does not block the application for too long.
OVERPASS_TIMEOUT = 12
NOMINATIM_TIMEOUT = 15

# Smaller default search radius reduces expensive Overpass queries.
DEFAULT_SEARCH_RADIUS = 8000


# =========================================================
# GEOCODE LOCATION
# =========================================================

def geocode_location(location):
    """
    Convert a location name into latitude and longitude.
    """

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                "q": location,
                "format": "json",
                "limit": 1
            },
            headers=HEADERS,
            timeout=NOMINATIM_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        if not data:
            print(
                f"No geocoding result found for: {location}"
            )
            return None

        result = data[0]

        return {
            "latitude": float(result["lat"]),
            "longitude": float(result["lon"]),
            "display_name": result.get(
                "display_name",
                location
            )
        }

    except requests.RequestException as error:
        print(
            f"Geocoding request failed for "
            f"{location}: {error}"
        )

    except (
        ValueError,
        KeyError,
        TypeError
    ) as error:
        print(
            f"Invalid geocoding response for "
            f"{location}: {error}"
        )

    return None


# =========================================================
# BUILD OVERPASS QUERY
# =========================================================

def build_overpass_query(
    latitude,
    longitude,
    radius=DEFAULT_SEARCH_RADIUS,
    categories=None
):
    """
    Build a lightweight Overpass query for named
    tourism-related places.

    The query intentionally focuses on elements that have
    names because unnamed OSM objects are not useful for
    displaying place cards to users.
    """

    if not categories:
        categories = [
            "tourism",
            "historic",
            "natural",
            "leisure"
        ]

    query_parts = []

    for category in categories:

        # -------------------------------------------------
        # TOURISM
        # -------------------------------------------------

        if category == "tourism":

            query_parts.extend([
                f'node["tourism"]["name"](around:{radius},{latitude},{longitude});',
                f'way["tourism"]["name"](around:{radius},{latitude},{longitude});',
                f'relation["tourism"]["name"](around:{radius},{latitude},{longitude});'
            ])

        # -------------------------------------------------
        # HISTORIC
        # -------------------------------------------------

        elif category == "historic":

            query_parts.extend([
                f'node["historic"]["name"](around:{radius},{latitude},{longitude});',
                f'way["historic"]["name"](around:{radius},{latitude},{longitude});',
                f'relation["historic"]["name"](around:{radius},{latitude},{longitude});'
            ])

        # -------------------------------------------------
        # NATURAL
        # -------------------------------------------------

        elif category == "natural":

            query_parts.extend([
                f'node["natural"]["name"](around:{radius},{latitude},{longitude});',
                f'way["natural"]["name"](around:{radius},{latitude},{longitude});',
                f'relation["natural"]["name"](around:{radius},{latitude},{longitude});'
            ])

        # -------------------------------------------------
        # LEISURE
        # -------------------------------------------------

        elif category == "leisure":

            query_parts.extend([
                f'node["leisure"]["name"](around:{radius},{latitude},{longitude});',
                f'way["leisure"]["name"](around:{radius},{latitude},{longitude});',
                f'relation["leisure"]["name"](around:{radius},{latitude},{longitude});'
            ])

        # -------------------------------------------------
        # AMENITY
        # -------------------------------------------------

        elif category == "amenity":

            query_parts.extend([
                f'node["amenity"]["name"](around:{radius},{latitude},{longitude});',
                f'way["amenity"]["name"](around:{radius},{latitude},{longitude});',
                f'relation["amenity"]["name"](around:{radius},{latitude},{longitude});'
            ])

    query = f"""
    [out:json][timeout:15];

    (
        {"".join(query_parts)}
    );

    out center tags;
    """

    return query


# =========================================================
# IMAGE URL
# =========================================================

def get_image_url(tags):

    if not tags:
        return None

    # -----------------------------------------------------
    # DIRECT IMAGE
    # -----------------------------------------------------

    image = tags.get("image")

    if image:
        return image

    # -----------------------------------------------------
    # WIKIMEDIA COMMONS
    # -----------------------------------------------------

    wikimedia = tags.get(
        "wikimedia_commons"
    )

    if wikimedia and wikimedia.startswith("File:"):

        filename = wikimedia.replace(
            "File:",
            "",
            1
        ).strip()

        return (
            "https://commons.wikimedia.org/"
            "wiki/Special:FilePath/"
            + requests.utils.quote(filename)
        )

    return None


# =========================================================
# DISTANCE
# =========================================================

def calculate_distance(
    lat1,
    lon1,
    lat2,
    lon2
):
    """
    Calculate distance between two coordinates.
    Returns distance in kilometers.
    """

    try:

        earth_radius = 6371.0

        lat1 = math.radians(float(lat1))
        lon1 = math.radians(float(lon1))
        lat2 = math.radians(float(lat2))
        lon2 = math.radians(float(lon2))

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2) ** 2
        )

        c = 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )

        return round(
            earth_radius * c,
            2
        )

    except (
        ValueError,
        TypeError,
        ZeroDivisionError
    ):
        return None


# =========================================================
# DETERMINE CATEGORY
# =========================================================

def determine_category(tags):

    if not tags:
        return "Other"

    tourism = tags.get(
        "tourism",
        ""
    ).lower()

    historic = tags.get(
        "historic",
        ""
    ).lower()

    natural = tags.get(
        "natural",
        ""
    ).lower()

    leisure = tags.get(
        "leisure",
        ""
    ).lower()

    amenity = tags.get(
        "amenity",
        ""
    ).lower()

    # -----------------------------------------------------
    # TOURIST ATTRACTIONS
    # -----------------------------------------------------

    if tourism in [
        "attraction",
        "museum",
        "gallery",
        "theme_park",
        "zoo",
        "viewpoint",
        "picnic_site",
        "information"
    ]:
        return "Tourist Attraction"

    # -----------------------------------------------------
    # ACCOMMODATION
    # -----------------------------------------------------

    if tourism in [
        "hotel",
        "hostel",
        "guest_house",
        "motel",
        "camp_site"
    ]:
        return "Accommodation"

    # -----------------------------------------------------
    # HISTORICAL
    # -----------------------------------------------------

    if historic:
        return "Historical"

    # -----------------------------------------------------
    # NATURE
    # -----------------------------------------------------

    if natural:
        return "Nature"

    # -----------------------------------------------------
    # LEISURE
    # -----------------------------------------------------

    if leisure:
        return "Leisure"

    # -----------------------------------------------------
    # FOOD
    # -----------------------------------------------------

    if amenity in [
        "restaurant",
        "cafe",
        "fast_food",
        "food_court"
    ]:
        return "Food"

    return "Other"


# =========================================================
# BUILD PLACE LOCATION
# =========================================================

def build_place_location(tags):

    if not tags:
        return "Location unavailable"

    address_parts = []

    for key in [
        "road",
        "neighbourhood",
        "suburb",
        "city",
        "town",
        "village",
        "state"
    ]:

        value = tags.get(key)

        if value and value not in address_parts:
            address_parts.append(value)

    if address_parts:
        return ", ".join(
            address_parts
        )

    return "Location unavailable"


# =========================================================
# DISCOVER PLACES
# =========================================================

def discover_places(
    latitude,
    longitude,
    radius=DEFAULT_SEARCH_RADIUS,
    categories=None,
    location_name=None
):
    """
    Discover tourism-related places using Overpass.

    location_name is accepted for compatibility with the
    existing app.py implementation.

    The function keeps the same output structure expected
    by the existing frontend and AI ranking system.
    """

    # -----------------------------------------------------
    # SAFETY LIMIT
    # -----------------------------------------------------

    try:
        radius = int(radius)

    except (
        ValueError,
        TypeError
    ):
        radius = DEFAULT_SEARCH_RADIUS

    # Prevent unnecessarily large public Overpass queries.
    radius = min(
        radius,
        DEFAULT_SEARCH_RADIUS
    )

    # -----------------------------------------------------
    # BUILD QUERY
    # -----------------------------------------------------

    query = build_overpass_query(
        latitude,
        longitude,
        radius,
        categories
    )

    data = None

    # -----------------------------------------------------
    # TRY MULTIPLE OVERPASS SERVERS
    # -----------------------------------------------------

    for server in OVERPASS_URLS:

        print(
            f"Trying Overpass server: {server}"
        )

        try:

            response = requests.post(
                server,
                data=query,
                headers=HEADERS,
                timeout=OVERPASS_TIMEOUT
            )

            response.raise_for_status()

            data = response.json()

            elements_count = len(
                data.get(
                    "elements",
                    []
                )
            )

            print(
                "Overpass response received: "
                f"{elements_count} elements"
            )

            break

        except requests.RequestException as error:

            print(
                f"Overpass server failed: "
                f"{server} {error}"
            )

            # Small delay before trying the next server.
            time.sleep(0.25)

        except ValueError as error:

            print(
                f"Invalid Overpass JSON response "
                f"from {server}: {error}"
            )

    # -----------------------------------------------------
    # ALL SERVERS FAILED
    # -----------------------------------------------------

    if not data:

        print(
            "All Overpass servers failed."
        )

        return []

    # -----------------------------------------------------
    # PROCESS ELEMENTS
    # -----------------------------------------------------

    places = []

    elements = data.get(
        "elements",
        []
    )

    for element in elements:

        try:

            tags = element.get(
                "tags",
                {}
            )

            if not tags:
                continue

            # -------------------------------------------------
            # NAME
            # -------------------------------------------------

            name = tags.get(
                "name"
            )

            if not name:
                continue

            # -------------------------------------------------
            # COORDINATES
            # -------------------------------------------------

            element_latitude = element.get(
                "lat"
            )

            element_longitude = element.get(
                "lon"
            )

            # Ways and relations normally provide a center.
            if (
                element_latitude is None
                or element_longitude is None
            ):

                center = element.get(
                    "center",
                    {}
                )

                element_latitude = center.get(
                    "lat"
                )

                element_longitude = center.get(
                    "lon"
                )

            if (
                element_latitude is None
                or element_longitude is None
            ):
                continue

            element_latitude = float(
                element_latitude
            )

            element_longitude = float(
                element_longitude
            )

            # -------------------------------------------------
            # OSM ID
            # -------------------------------------------------

            osm_type = element.get(
                "type"
            )

            osm_id = element.get(
                "id"
            )

            if osm_type and osm_id:

                place_id = (
                    f"{osm_type}_{osm_id}"
                )

            else:

                place_id = str(
                    osm_id
                )

            # -------------------------------------------------
            # DISTANCE
            # -------------------------------------------------

            distance = calculate_distance(
                latitude,
                longitude,
                element_latitude,
                element_longitude
            )

            # -------------------------------------------------
            # CATEGORY
            # -------------------------------------------------

            category = determine_category(
                tags
            )

            # -------------------------------------------------
            # DESCRIPTION
            # -------------------------------------------------

            description = (
                tags.get("description")
                or tags.get("short_description")
                or (
                    f"{name} is a "
                    f"{category.lower()} destination."
                )
            )

            # -------------------------------------------------
            # IMAGE
            # -------------------------------------------------

            image_url = get_image_url(
                tags
            )

            # -------------------------------------------------
            # LOCATION
            # -------------------------------------------------

            location = build_place_location(
                tags
            )

            # -------------------------------------------------
            # ADD PLACE
            # -------------------------------------------------

            places.append({

                "id": place_id,

                "osm_id": place_id,

                "osm_type": osm_type,

                "name": name,

                "latitude": element_latitude,

                "longitude": element_longitude,

                "location": location,

                "category": category,

                "description": description,

                "image": image_url,

                "distance_km": distance,

                "tags": tags
            })

        except (
            ValueError,
            TypeError,
            KeyError
        ) as error:

            print(
                f"Skipping invalid OSM element: "
                f"{error}"
            )

            continue

    # =====================================================
    # DEDUPLICATE
    # =====================================================

    places = deduplicate_places(
        places
    )

    print(
        "Final unique places discovered: "
        f"{len(places)}"
    )

    return places


# =========================================================
# GET SINGLE OSM PLACE
# =========================================================

def get_place_by_osm_id(osm_id):

    if not osm_id:
        return None

    # -----------------------------------------------------
    # VALIDATE OSM ID
    # -----------------------------------------------------

    try:

        if "_" not in osm_id:

            print(
                f"Invalid OSM ID: {osm_id}"
            )

            return None

        osm_type, raw_id = osm_id.split(
            "_",
            1
        )

        if osm_type not in [
            "node",
            "way",
            "relation"
        ]:

            print(
                f"Unsupported OSM type: {osm_type}"
            )

            return None

        int(raw_id)

    except (
        ValueError,
        TypeError
    ):

        print(
            f"Invalid OSM ID: {osm_id}"
        )

        return None

    # -----------------------------------------------------
    # SINGLE PLACE QUERY
    # -----------------------------------------------------

    query = f"""
    [out:json][timeout:10];

    {osm_type}({raw_id});

    out center tags;
    """

    data = None

    # -----------------------------------------------------
    # TRY MULTIPLE SERVERS
    # -----------------------------------------------------

    for server in OVERPASS_URLS:

        print(
            f"Trying Overpass server for place: "
            f"{server}"
        )

        try:

            response = requests.post(
                server,
                data=query,
                headers=HEADERS,
                timeout=OVERPASS_TIMEOUT
            )

            response.raise_for_status()

            data = response.json()

            break

        except requests.RequestException as error:

            print(
                f"Overpass place lookup failed: "
                f"{server} {error}"
            )

        except ValueError as error:

            print(
                f"Invalid Overpass place response: "
                f"{error}"
            )

    # -----------------------------------------------------
    # NO DATA
    # -----------------------------------------------------

    if not data:

        print(
            "Unable to retrieve OSM place."
        )

        return None

    elements = data.get(
        "elements",
        []
    )

    if not elements:
        return None

    element = elements[0]

    tags = element.get(
        "tags",
        {}
    )

    # -----------------------------------------------------
    # COORDINATES
    # -----------------------------------------------------

    latitude = element.get(
        "lat"
    )

    longitude = element.get(
        "lon"
    )

    if (
        latitude is None
        or longitude is None
    ):

        center = element.get(
            "center",
            {}
        )

        latitude = center.get(
            "lat"
        )

        longitude = center.get(
            "lon"
        )

    if (
        latitude is None
        or longitude is None
    ):
        return None

    try:

        latitude = float(
            latitude
        )

        longitude = float(
            longitude
        )

    except (
        ValueError,
        TypeError
    ):

        return None

    # -----------------------------------------------------
    # PLACE INFORMATION
    # -----------------------------------------------------

    name = tags.get(
        "name",
        "Unknown Destination"
    )

    category = determine_category(
        tags
    )

    description = (
        tags.get("description")
        or tags.get("short_description")
        or (
            f"{name} is a "
            f"{category.lower()} destination."
        )
    )

    image_url = get_image_url(
        tags
    )

    location = build_place_location(
        tags
    )

    return {

        "id": osm_id,

        "osm_id": osm_id,

        "osm_type": element.get(
            "type"
        ),

        "name": name,

        "latitude": latitude,

        "longitude": longitude,

        "location": location,

        "category": category,

        "description": description,

        "image": image_url,

        "distance_km": None,

        "tags": tags
    }


# =========================================================
# DEDUPLICATE PLACES
# =========================================================

def deduplicate_places(places):

    if not places:
        return []

    unique_places = []

    seen = set()

    for place in places:

        if not place:
            continue

        name = str(
            place.get(
                "name",
                ""
            )
        ).strip().lower()

        latitude = place.get(
            "latitude"
        )

        longitude = place.get(
            "longitude"
        )

        if (
            not name
            or latitude is None
            or longitude is None
        ):
            continue

        try:

            key = (
                name,
                round(
                    float(latitude),
                    4
                ),
                round(
                    float(longitude),
                    4
                )
            )

        except (
            ValueError,
            TypeError
        ):

            continue

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_places.append(
            place
        )

    # -----------------------------------------------------
    # SORT BY DISTANCE
    # -----------------------------------------------------

    unique_places.sort(
        key=lambda place: (
            place.get(
                "distance_km"
            )
            if place.get(
                "distance_km"
            ) is not None
            else float("inf")
        )
    )

    return unique_places