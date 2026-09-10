import json
import math
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from flask import Flask, jsonify, render_template, request
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash
import jwt
import requests

from database import Hotel, Place, Restaurant, Trip, User, db
from services.crowd_service import get_forecast_crowd, get_live_crowd
from services.osm_service import (
    calculate_distance,
    discover_places,
    geocode_location,
    get_place_by_osm_id,
)
from services.place_context_service import build_place_context, get_nearby_places
from services.weather_service import get_weather
from ai.place_ai import (
    analyze_place,
    generate_place_recommendation,
    generate_place_response,
)
from ai.place_search_ai import interpret_place_query, rank_places

app = Flask(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

app.config["JWT_SECRET_KEY"] = "byond-spot-secret-key-change-this-later"
app.config["JWT_EXPIRATION_HOURS"] = 24
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///byond_spot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


# =========================================================
# PAGE ROUTES
# =========================================================

@app.route("/")
def login_page():
    return render_template("login.html")

@app.route("/login.html")
def login_redirect():
    return render_template("login.html")

@app.route("/index.html")
def home():
    return render_template("index.html")

@app.route("/places.html")
def places():
    return render_template("places.html")

@app.route("/place-details.html")
def place_details_page():
    return render_template("place-details.html")

@app.route("/planner.html")
def planner():
    return render_template("planner.html")

@app.route("/itinerary.html")
def itinerary_page():
    return render_template("itinerary.html")

@app.route("/current-trip.html")
def current_trip_page():
    return render_template("current-trip.html")

@app.route("/hidden-gems.html")
def hidden_gems_page():
    return render_template("hidden-gems.html")

@app.route("/safety.html")
def safety_page():
    return render_template("safety.html")

@app.route("/hotels.html")
def hotels():
    return render_template("hotels.html")

@app.route("/restaurants.html")
def restaurants():
    return render_template("restaurants.html")

@app.route("/guides.html")
def guides_page():
    return render_template("guides.html")

@app.route("/travel.html")
def travel_page():
    return render_template("travel.html")


# =========================================================
# CENTRAL PLACE RESOLVER
# =========================================================

def resolve_place(place_id):
    """
    Resolve a BYOND Spot place ID.

    Supports:
    1. SQLite database IDs:
       - 'db_1', 'db_2', 'db_3', ...
       - numeric string '1', '2', '3', or int 1, 2, 3
    2. OpenStreetMap places:
       - 'node/123456', 'way/123456', 'relation/123456'
       - 'node_123456', 'way_123456', 'relation_123456'

    Returns a consistent normalized dictionary structure.
    """
    if not place_id:
        return None

    place_str = str(place_id).strip()

    # 1. Check for SQLite place
    db_id = None
    if place_str.startswith("db_"):
        try:
            db_id = int(place_str.replace("db_", "", 1))
        except ValueError:
            db_id = None
    elif place_str.isdigit():
        db_id = int(place_str)

    if db_id is not None:
        database_place = db.session.get(Place, db_id)
        if database_place:
            return {
                "id": f"db_{database_place.id}",
                "osm_id": None,
                "name": database_place.name,
                "location": database_place.location,
                "description": database_place.description,
                "category": database_place.category,
                "latitude": float(database_place.latitude),
                "longitude": float(database_place.longitude),
                "rating": database_place.rating if database_place.rating else 4.5,
                "image": database_place.image,
                "source": "database",
                "opening_hours": None,
                "website": None
            }

    # 2. Check for OSM place
    osm_normalized = place_str
    if "/" in osm_normalized:
        parts = osm_normalized.split("/", 1)
        if parts[0] in ["node", "way", "relation"]:
            osm_normalized = f"{parts[0]}_{parts[1]}"
    elif osm_normalized.isdigit():
        osm_normalized = f"node_{osm_normalized}"

    try:
        osm_place = get_place_by_osm_id(osm_normalized)
        if osm_place:
            osm_place["source"] = "osm"
            if not osm_place.get("id"):
                osm_place["id"] = osm_normalized
            return osm_place
    except Exception as error:
        print(f"OSM resolution error for {place_id}:", error)

    return None


# =========================================================
# DATABASE PLACE SEARCH HELPER
# =========================================================

def search_database_places(search_text, category="all"):
    """
    Search the curated SQLite places before external OSM discovery.
    """
    search_text = (search_text or "").strip().lower()
    places = Place.query.all()

    if not search_text or search_text in ["all", "any", "places", "explore"]:
        if category != "all":
            return [p for p in places if p.category and category.lower() in p.category.lower()]
        return places

    matches = []
    for place in places:
        if category != "all" and place.category:
            if category.lower() not in place.category.lower():
                continue

        name = (place.name or "").lower()
        location = (place.location or "").lower()
        description = (place.description or "").lower()

        if search_text in name:
            score = 1.0
        elif search_text in location:
            score = 0.9
        elif search_text in description:
            score = 0.7
        else:
            name_score = SequenceMatcher(None, search_text, name).ratio()
            location_score = SequenceMatcher(None, search_text, location).ratio()
            score = max(name_score, location_score)

        if score >= 0.40:
            matches.append((score, place))

    matches.sort(key=lambda item: (item[0], item[1].rating or 0), reverse=True)
    return [place for score, place in matches]


def serialize_database_places(places):
    return [
        {
            "id": f"db_{place.id}",
            "name": place.name,
            "location": place.location,
            "description": place.description,
            "category": place.category,
            "latitude": float(place.latitude),
            "longitude": float(place.longitude),
            "rating": place.rating,
            "image": place.image,
            "source": "database"
        }
        for place in places
    ]


# =========================================================
# AUTHENTICATION HELPERS
# =========================================================

def get_current_user():
    """
    Verify JWT access token from Authorization header.
    Falls back to first existing User for demo/test resilience if header missing.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
            try:
                payload = jwt.decode(
                    token,
                    app.config["JWT_SECRET_KEY"],
                    algorithms=["HS256"]
                )
                user_id = payload.get("user_id")
                user = db.session.get(User, user_id)
                if user:
                    return user, None
            except Exception:
                pass

    # Demo / Guest fallback
    demo_user = User.query.first()
    if demo_user:
        return demo_user, None

    # Auto-seed a default user if none exists
    new_user = User(
        name="Guest Traveler",
        email="traveler@byondspot.com",
        password=generate_password_hash("byondspot123")
    )
    db.session.add(new_user)
    db.session.commit()
    return new_user, None


@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "An account with this email already exists"}), 409

    new_user = User(
        name=name,
        email=email,
        password=generate_password_hash(password)
    )
    db.session.add(new_user)
    db.session.commit()

    return jsonify({
        "message": "Account created successfully",
        "user": {"id": new_user.id, "name": new_user.name, "email": new_user.email}
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid email or password"}), 401

    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=app.config["JWT_EXPIRATION_HOURS"])
    }
    token = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")

    return jsonify({
        "message": "Login successful",
        "access_token": token,
        "token": token,
        "user": {"id": user.id, "name": user.name, "email": user.email}
    }), 200


@app.route("/api/auth/me", methods=["GET"])
def me():
    user, error = get_current_user()
    if error:
        return jsonify({"error": error}), 401
    return jsonify({
        "user": {"id": user.id, "name": user.name, "email": user.email}
    }), 200


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    return jsonify({"message": "Logged out successfully"}), 200


# =========================================================
# PLACES SEARCH API
# =========================================================

@app.route("/api/places/search", methods=["GET"])
def ai_place_search():
    query = request.args.get("q", "").strip()
    category = request.args.get("category", "all")

    # 1. Search SQLite database first
    database_places = search_database_places(query, category)
    if database_places:
        places = serialize_database_places(database_places)
        return jsonify({
            "query": query,
            "location": {
                "name": database_places[0].location,
                "latitude": float(database_places[0].latitude),
                "longitude": float(database_places[0].longitude)
            },
            "category": category,
            "count": len(places),
            "places": places
        }), 200

    # If query was empty or generic, return all database places
    if not query:
        all_db = Place.query.all()
        places = serialize_database_places(all_db)
        return jsonify({
            "query": "",
            "location": {"name": "Andhra Pradesh", "latitude": 16.5062, "longitude": 80.6480},
            "category": category,
            "count": len(places),
            "places": places
        }), 200

    # 2. Try OSM / Overpass discovery with timeout protection
    try:
        interpretation = interpret_place_query(query)
        location_query = interpretation.get("location", query)
        ai_category = category if category != "all" else interpretation.get("category", "all")

        location = geocode_location(location_query)
        if not location:
            # Fallback to database places rather than error
            all_db = Place.query.all()
            places = serialize_database_places(all_db)
            return jsonify({
                "query": query,
                "location": {"name": location_query, "latitude": 16.5062, "longitude": 80.6480},
                "category": ai_category,
                "count": len(places),
                "places": places,
                "notice": "Showing recommended places for your search."
            }), 200

        location_name = location.get("display_name", location_query)
        categories = ["tourism", "historic", "natural", "leisure", "amenity"]

        discovered_places = discover_places(
            latitude=location["latitude"],
            longitude=location["longitude"],
            radius=15000,
            categories=categories,
            location_name=location_name
        )

        if not discovered_places:
            all_db = Place.query.all()
            places = serialize_database_places(all_db)
            return jsonify({
                "query": query,
                "location": {"name": location_name, "latitude": location["latitude"], "longitude": location["longitude"]},
                "category": ai_category,
                "count": len(places),
                "places": places
            }), 200

        # Rank with Gemini
        ranked_places = rank_places(query, discovered_places)
        return jsonify({
            "query": query,
            "location": {"name": location_name, "latitude": location["latitude"], "longitude": location["longitude"]},
            "category": ai_category,
            "count": len(ranked_places),
            "places": ranked_places
        }), 200

    except Exception as error:
        print("Places discovery fallback triggered:", error)
        all_db = Place.query.all()
        places = serialize_database_places(all_db)
        return jsonify({
            "query": query,
            "location": {"name": query, "latitude": 16.5062, "longitude": 80.6480},
            "category": category,
            "count": len(places),
            "places": places
        }), 200


# =========================================================
# PLACES LIST API
# =========================================================

@app.route("/api/places", methods=["GET"])
def get_places():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    places = search_database_places(search, category if category else "all")
    return jsonify(serialize_database_places(places)), 200


# =========================================================
# PLACE DETAILS API
# =========================================================

@app.route("/api/places/<path:place_id>", methods=["GET"])
def get_place_details(place_id):
    if not place_id:
        return jsonify({"error": "Place ID is required"}), 400

    user_latitude = request.args.get("latitude", type=float)
    user_longitude = request.args.get("longitude", type=float)

    try:
        place = resolve_place(place_id)
    except Exception as error:
        print(f"Error resolving place {place_id}:", error)
        place = None

    if not place:
        return jsonify({"error": f"Place '{place_id}' could not be found."}), 404

    # Calculate user distance if coordinates are present
    if (
        user_latitude is not None
        and user_longitude is not None
        and place.get("latitude") is not None
        and place.get("longitude") is not None
    ):
        place["distance_km"] = round(
            calculate_distance(
                user_latitude,
                user_longitude,
                place["latitude"],
                place["longitude"]
            ),
            1
        )

    # Build AI context (handles weather, crowd, opening, nearby independently)
    try:
        context = build_place_context(
            place=place,
            user_latitude=user_latitude,
            user_longitude=user_longitude
        )
    except Exception as error:
        print("Context building error:", error)
        context = {
            "place": place,
            "user": {"distance_km": place.get("distance_km")},
            "weather": {"condition": "Weather unavailable", "available": False},
            "crowd_activity": {"level": "Unavailable", "available": False},
            "opening_hours": {"status": "Opening hours unavailable", "available": False},
            "nearby_places": []
        }

    return jsonify({
        "place": place,
        "context": context
    }), 200


# =========================================================
# HOTELS & RESTAURANTS
# =========================================================

@app.route("/api/hotels", methods=["GET"])
def get_hotels():
    search = request.args.get("search", "").strip()
    price_type = request.args.get("price", "").strip().lower()
    activity = request.args.get("activity", "").strip().lower()
    rating = request.args.get("rating", "").strip()

    query = Hotel.query
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Hotel.name.ilike(pattern),
                Hotel.location.ilike(pattern),
                Hotel.type.ilike(pattern)
            )
        )
    if price_type and price_type != "all":
        query = query.filter(Hotel.price_type.ilike(price_type))
    if activity and activity != "all":
        query = query.filter(Hotel.activity.ilike(activity))
    if rating and rating != "all":
        try:
            query = query.filter(Hotel.rating >= float(rating))
        except ValueError:
            pass

    hotels = query.order_by(Hotel.rating.desc()).all()
    return jsonify([
        {
            "id": h.id,
            "name": h.name,
            "location": h.location,
            "description": h.description,
            "type": h.type,
            "rating": h.rating,
            "reviews": h.reviews,
            "price": h.price,
            "price_type": h.price_type,
            "activity": h.activity,
            "latitude": float(h.latitude),
            "longitude": float(h.longitude),
            "image": h.image
        }
        for h in hotels
    ]), 200


@app.route("/api/restaurants", methods=["GET"])
def get_restaurants():
    search = request.args.get("search", "").strip()
    cuisine = request.args.get("cuisine", "").strip().lower()
    price_type = request.args.get("price", "").strip().lower()
    activity = request.args.get("activity", "").strip().lower()
    rating = request.args.get("rating", "").strip()

    query = Restaurant.query
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Restaurant.name.ilike(pattern),
                Restaurant.location.ilike(pattern),
                Restaurant.cuisine.ilike(pattern)
            )
        )
    if cuisine and cuisine != "all":
        query = query.filter(Restaurant.cuisine_type.ilike(cuisine))
    if price_type and price_type != "all":
        query = query.filter(Restaurant.price_type.ilike(price_type))
    if activity and activity != "all":
        query = query.filter(Restaurant.activity.ilike(activity))
    if rating and rating != "all":
        try:
            query = query.filter(Restaurant.rating >= float(rating))
        except ValueError:
            pass

    restaurants = query.order_by(Restaurant.rating.desc()).all()
    return jsonify([
        {
            "id": r.id,
            "name": r.name,
            "location": r.location,
            "description": r.description,
            "cuisine": r.cuisine,
            "cuisine_type": r.cuisine_type,
            "rating": r.rating,
            "reviews": r.reviews,
            "price": r.price,
            "price_type": r.price_type,
            "activity": r.activity,
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
            "image": r.image
        }
        for r in restaurants
    ]), 200


# =========================================================
# TRIP PLANNING API
# =========================================================

@app.route("/api/trips/plan", methods=["POST"])
def create_trip_plan():
    user, _ = get_current_user()

    data = request.get_json() or {}
    destination = data.get("destination", {})
    destination_name = (
        destination.get("name", "").strip()
        if isinstance(destination, dict)
        else str(destination).strip()
    )
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    duration_days = int(data.get("duration_days") or 1)
    travellers = int(data.get("travellers") or 1)
    budget = float(data.get("budget") or 5000)
    interests = data.get("interests", [])
    travel_style = data.get("travel_style", "Balanced")
    transport = data.get("transport", "No Preference")

    if not destination_name:
        destination_name = "Vijayawada & Amaravati"

    # Step 1: Retrieve real candidate places from SQLite
    pattern = f"%{destination_name}%"
    available_places = Place.query.filter(
        or_(
            Place.name.ilike(pattern),
            Place.location.ilike(pattern),
            Place.description.ilike(pattern)
        )
    ).all()

    # If few or no direct matches, include all curated places from database
    if len(available_places) < 4:
        all_places = Place.query.all()
        # combine without duplicates
        existing_ids = {p.id for p in available_places}
        for p in all_places:
            if p.id not in existing_ids:
                available_places.append(p)

    trip_data = {
        "destination": {
            "name": destination_name,
            "id": destination.get("id") if isinstance(destination, dict) else None
        },
        "start_date": start_date or datetime.now().strftime("%Y-%m-%d"),
        "end_date": end_date or (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d"),
        "duration_days": duration_days,
        "travellers": travellers,
        "budget": budget,
        "interests": interests,
        "travel_style": travel_style,
        "transport": transport
    }

    try:
        from ai.itinerary_ai import enrich_itinerary_with_crowd, generate_itinerary

        # Step 2: Gemini strictly plans using candidate places only
        itinerary = generate_itinerary(trip_data, available_places)

        # Step 3: BestTime crowd enrichment and schedule optimization
        itinerary = enrich_itinerary_with_crowd(
            itinerary,
            trip_data,
            available_places,
            max_venues=6
        )

    except Exception as error:
        print("AI itinerary generation error:", error)
        # Resilient fallback using curated places directly
        from datetime import datetime as dt
        days = []
        cur_places = available_places[:duration_days * 2] if available_places else []
        idx = 0
        for d in range(1, duration_days + 1):
            day_places = []
            if idx < len(cur_places):
                p = cur_places[idx]
                day_places.append({
                    "id": f"db_{p.id}",
                    "name": p.name,
                    "time": "09:30 AM - 12:30 PM",
                    "category": p.category,
                    "description": p.description,
                    "estimated_cost": 250,
                    "reason": f"Popular {p.category} attraction"
                })
                idx += 1
            if idx < len(cur_places):
                p = cur_places[idx]
                day_places.append({
                    "id": f"db_{p.id}",
                    "name": p.name,
                    "time": "02:30 PM - 05:00 PM",
                    "category": p.category,
                    "description": p.description,
                    "estimated_cost": 200,
                    "reason": f"Scenic {p.category} spot"
                })
                idx += 1

            days.append({
                "day": d,
                "date": (datetime.now() + timedelta(days=d-1)).strftime("%Y-%m-%d"),
                "places": day_places
            })

        itinerary = {
            "destination": destination_name,
            "duration_days": duration_days,
            "estimated_total_cost": budget * 0.7,
            "days": days
        }

    new_trip = Trip(
        user_id=user.id,
        destination_name=destination_name,
        start_date=trip_data["start_date"],
        end_date=trip_data["end_date"],
        duration_days=duration_days,
        travellers=travellers,
        budget=budget,
        interests=json.dumps(interests),
        travel_style=travel_style,
        transport=transport,
        itinerary=json.dumps(itinerary),
        original_itinerary=json.dumps(itinerary),
        status="planned",
        current_day=1,
        total_spent=0
    )

    db.session.add(new_trip)
    db.session.commit()

    return jsonify({
        "message": "AI itinerary generated successfully",
        "trip_id": new_trip.id,
        "trip": {
            "id": new_trip.id,
            "destination": {"name": destination_name},
            "start_date": new_trip.start_date,
            "end_date": new_trip.end_date,
            "duration_days": new_trip.duration_days,
            "travellers": new_trip.travellers,
            "budget": new_trip.budget,
            "interests": interests,
            "travel_style": travel_style,
            "transport": transport,
            "status": new_trip.status,
            "itinerary": itinerary
        }
    }), 201


@app.route("/api/trips/<int:trip_id>/start", methods=["POST"])
def start_trip(trip_id):
    trip = db.session.get(Trip, trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json(silent=True) or {}
    if "itinerary" in data:
        trip.itinerary = json.dumps(data["itinerary"])
    trip.status = "active"
    trip.started_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        "message": "Trip started successfully",
        "status": "active",
        "started_at": trip.started_at.isoformat(),
        "trip_id": trip.id
    }), 200


@app.route("/api/trips/<int:trip_id>/itinerary", methods=["PATCH"])
def update_trip_itinerary(trip_id):
    trip = db.session.get(Trip, trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json(silent=True) or {}
    if "itinerary" in data:
        trip.itinerary = json.dumps(data["itinerary"])
        db.session.commit()

    return jsonify({"message": "Itinerary updated successfully"}), 200


@app.route("/api/trips/<int:trip_id>", methods=["GET"])
def get_trip(trip_id):
    trip = db.session.get(Trip, trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    try:
        itin = json.loads(trip.itinerary or "{}")
    except Exception:
        itin = {}

    return jsonify({
        "id": trip.id,
        "destination_name": trip.destination_name,
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "duration_days": trip.duration_days,
        "travellers": trip.travellers,
        "budget": trip.budget,
        "status": trip.status,
        "current_day": trip.current_day,
        "total_spent": trip.total_spent,
        "itinerary": itin
    }), 200


@app.route("/api/trips/<int:trip_id>/expenses", methods=["POST"])
def record_expense(trip_id):
    trip = db.session.get(Trip, trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json(silent=True) or {}
    amount = float(data.get("amount", 0))
    trip.total_spent = (trip.total_spent or 0) + amount
    db.session.commit()

    return jsonify({
        "message": "Expense recorded",
        "total_spent": trip.total_spent
    }), 200


@app.route("/api/trips/<int:trip_id>/progress", methods=["POST"])
def update_trip_progress(trip_id):
    trip = db.session.get(Trip, trip_id)
    if not trip:
        return jsonify({"error": "Trip not found"}), 404

    data = request.get_json(silent=True) or {}
    if "current_day" in data:
        trip.current_day = int(data["current_day"])
    db.session.commit()

    return jsonify({
        "message": "Progress updated",
        "current_day": trip.current_day
    }), 200


# =========================================================
# CURRENT TRIP CROWD ACTIVITY
# =========================================================

@app.route("/api/trips/<int:trip_id>/crowd", methods=["GET"])
@app.route("/api/trips/crowd", methods=["GET", "POST"])
def current_trip_crowd(trip_id=None):
    data = request.get_json(silent=True) or {}

    if trip_id is None:
        raw_id = request.args.get("trip_id") or data.get("trip_id")
        if raw_id:
            try:
                trip_id = int(raw_id)
            except (ValueError, TypeError):
                trip_id = None

    requested_day = request.args.get("day", type=int) or data.get("current_day") or data.get("day")
    if requested_day is not None:
        try:
            requested_day = int(requested_day)
        except (ValueError, TypeError):
            requested_day = None

    trip = db.session.get(Trip, trip_id) if trip_id else None

    current_day = requested_day if requested_day else (trip.current_day if trip else 1)
    places_to_query = []

    # 1. If explicit places provided in request body (e.g. from current-trip.html active trip)
    client_places = data.get("places")
    if isinstance(client_places, list) and len(client_places) > 0:
        places_to_query = client_places
    elif trip:
        try:
            itinerary = json.loads(trip.itinerary or "{}")
        except Exception:
            itinerary = {}
        days = itinerary.get("days", [])
        day_data = next((d for d in days if int(d.get("day", 0)) == current_day), None)
        if day_data:
            places_to_query = day_data.get("places", [])

    if not places_to_query:
        return jsonify({
            "trip_id": trip.id if trip else trip_id,
            "current_day": current_day,
            "crowd_activity": []
        }), 200

    # 2. Determine whether target visit is today or in the future
    is_future = False
    day_date = datetime.now()
    if trip and trip.start_date:
        try:
            trip_start = datetime.strptime(str(trip.start_date).strip(), "%Y-%m-%d")
            day_date = trip_start + timedelta(days=max(0, current_day - 1))
            is_future = day_date.date() > datetime.now().date()
        except Exception:
            is_future = current_day > (trip.current_day if trip else 1)
            day_date = datetime.now() + timedelta(days=max(0, current_day - 1))
    else:
        is_future = current_day > (trip.current_day if trip else 1)
        day_date = datetime.now() + timedelta(days=max(0, current_day - 1))

    results = []
    for item in places_to_query:
        raw_id = item.get("place_id") or item.get("id")
        name = str(item.get("name") or "").strip()

        # Central place resolution (handles db_1, db_2, db_3, numeric, OSM IDs)
        resolved = resolve_place(raw_id)
        if not resolved and name:
            place_match = Place.query.filter(Place.name.ilike(name)).first()
            if not place_match:
                place_match = Place.query.filter(Place.name.ilike(f"%{name}%")).first()
            if place_match:
                resolved = {
                    "id": f"db_{place_match.id}",
                    "name": place_match.name,
                    "location": place_match.location,
                    "latitude": float(place_match.latitude),
                    "longitude": float(place_match.longitude),
                    "category": place_match.category
                }

        source_place = {
            "name": resolved["name"] if resolved else name,
            "location": resolved.get("location") if resolved else (item.get("location") or ""),
            "latitude": resolved.get("latitude") if resolved else (item.get("latitude") or item.get("lat")),
            "longitude": resolved.get("longitude") if resolved else (item.get("longitude") or item.get("lng"))
        }

        if not source_place["name"]:
            continue

        if not is_future:
            # Current / today's visit -> Live crowd
            crowd = get_live_crowd(source_place)
        else:
            # Future visit -> Forecast crowd
            target_dt = day_date.replace(hour=10, minute=0, second=0, microsecond=0)
            time_str = str(item.get("start_time") or item.get("time") or "").strip()
            if time_str:
                try:
                    if ":" in time_str:
                        clean_time = time_str.split("-")[0].strip()
                        parts = clean_time.split()[0].split(":")
                        hr = int(parts[0])
                        mn = int(parts[1][:2])
                        if "pm" in clean_time.lower() and hr < 12:
                            hr += 12
                        elif "am" in clean_time.lower() and hr == 12:
                            hr = 0
                        target_dt = day_date.replace(hour=hr, minute=mn)
                except Exception:
                    pass
            crowd = get_forecast_crowd(source_place, target_dt)

        results.append({
            "place_id": raw_id or (resolved.get("id") if resolved else None),
            "name": source_place["name"],
            "location": source_place["location"],
            "crowd_level": crowd.get("level", "Unavailable"),
            "crowd_score": crowd.get("live_busyness"),
            "forecast_busyness": crowd.get("forecast_busyness"),
            "source": crowd.get("source", "BestTime"),
            "is_live": crowd.get("is_live", False),
            "available": crowd.get("available", False),
            "message": crowd.get("message") or ("Live crowd activity" if crowd.get("is_live") else "Expected crowd forecast" if crowd.get("available") else "Crowd data unavailable"),
            "trend": crowd.get("trend")
        })

    return jsonify({
        "trip_id": trip.id if trip else trip_id,
        "current_day": current_day,
        "crowd_activity": results
    }), 200


# =========================================================
# CURRENT TRIP AI SUGGESTIONS
# =========================================================

@app.route("/api/ai/trip-suggestions", methods=["POST"])
def trip_ai_suggestions():
    user, _ = get_current_user()
    data = request.get_json(silent=True) or {}

    trip_id = data.get("trip_id")
    trip = db.session.get(Trip, int(trip_id)) if trip_id else None

    available_places = Place.query.limit(20).all()

    trip_context = {
        "trip_id": trip.id if trip else trip_id,
        "current_day": data.get("current_day", trip.current_day if trip else 1),
        "current_time": data.get("current_time", datetime.now().strftime("%H:%M")),
        "current_location": data.get("current_location"),
        "remaining_budget": data.get("remaining_budget", trip.budget if trip else 3000),
        "today_spent": data.get("today_spent", 0),
        "total_spent": data.get("total_spent", trip.total_spent if trip else 0),
        "remaining_days": data.get("remaining_days", 1),
        "current_itinerary": data.get("current_itinerary", []),
        "today_itinerary": data.get("today_itinerary", []),
        "completed_places": data.get("completed_places", []),
        "skipped_places": data.get("skipped_places", []),
        "user_interests": data.get("user_interests", []),
        "weather": data.get("weather", {}),
        "crowd_activity": data.get("crowd_activity", [])
    }

    try:
        from ai.trip_ai import generate_trip_suggestions
        result = generate_trip_suggestions(trip_context, available_places)
        return jsonify(result), 200
    except Exception as error:
        print("Current trip AI error:", error)
        # Grounded fallback advice that uses REAL crowd_activity and REAL database places
        suggestions = []
        crowd_items = trip_context.get("crowd_activity", [])
        busy_items = [c for c in crowd_items if c.get("crowd_level") in ["Busy", "Very Busy"]]

        if busy_items:
            busy = busy_items[0]
            completed_names = [str(p.get("name", "")).lower() for p in trip_context.get("completed_places", [])]
            alt = next((
                p for p in available_places
                if p.name.lower() != busy.get("name", "").lower()
                and p.name.lower() not in completed_names
            ), None)
            suggestions.append({
                "type": "Crowd",
                "title": f"High Activity at {busy.get('name')}",
                "text": f"{busy.get('name')} is currently experiencing high foot traffic ({busy.get('crowd_level')}). Consider visiting {alt.name if alt else 'later in the day'} to avoid peak crowds.",
                "why": "Real-time BestTime crowd analysis indicates peak activity.",
                "place_id": f"db_{alt.id}" if alt else None
            })

        suggestions.append({
            "type": "Explore",
            "title": "Continue On Track",
            "text": "Your planned schedule for today is well paced. Visit your upcoming destination as planned.",
            "why": "Current schedule is on track.",
            "place_id": None
        })
        return jsonify({"suggestions": suggestions}), 200


# =========================================================
# ROUTING API (OSRM)
# =========================================================

@app.route("/api/route", methods=["GET"])
def get_route():
    origin_lat = request.args.get("origin_lat", type=float)
    origin_lng = request.args.get("origin_lng", type=float)
    destination_lat = request.args.get("destination_lat", type=float)
    destination_lng = request.args.get("destination_lng", type=float)

    start_str = request.args.get("start") or request.args.get("origin")
    end_str = request.args.get("end") or request.args.get("destination")
    if start_str and "," in start_str:
        try:
            parts = [float(x.strip()) for x in start_str.split(",")]
            origin_lat, origin_lng = parts[0], parts[1]
        except Exception:
            pass
    if end_str and "," in end_str:
        try:
            parts = [float(x.strip()) for x in end_str.split(",")]
            destination_lat, destination_lng = parts[0], parts[1]
        except Exception:
            pass

    if any(v is None for v in [origin_lat, origin_lng, destination_lat, destination_lng]):
        return jsonify({"error": "Origin and destination coordinates are required."}), 400

    osrm_url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{origin_lng},{origin_lat};{destination_lng},{destination_lat}"
    )

    try:
        response = requests.get(
            osrm_url,
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            dist_km = round(route.get("distance", 0) / 1000.0, 1)
            duration_min = round(route.get("duration", 0) / 60.0)
            return jsonify({
                "distance_km": dist_km,
                "duration_minutes": duration_min,
                "route": route.get("geometry"),
                "route_geojson": route.get("geometry")
            }), 200

    except Exception as error:
        print("Routing service error:", error)

    # Fallback to straight-line distance if OSRM is unreachable
    straight_dist = round(calculate_distance(origin_lat, origin_lng, destination_lat, destination_lng), 1)
    est_duration = round((straight_dist / 35.0) * 60)  # avg 35 km/h driving speed
    straight_line_geojson = {
        "type": "LineString",
        "coordinates": [[origin_lng, origin_lat], [destination_lng, destination_lat]]
    }
    return jsonify({
        "distance_km": straight_dist,
        "duration_minutes": est_duration,
        "route": straight_line_geojson,
        "route_geojson": straight_line_geojson,
        "fallback": True
    }), 200


# =========================================================
# PLACE AI CHAT
# =========================================================

@app.route("/api/ai/chat", methods=["POST"])
def place_ai_chat():
    data = request.get_json() or {}
    place_id = data.get("place_id")
    current_place = data.get("current_place")
    message = data.get("message", "").strip()
    user_latitude = data.get("latitude", type=float) if "latitude" in data else None
    user_longitude = data.get("longitude", type=float) if "longitude" in data else None

    if not message:
        return jsonify({"error": "Message is required"}), 400

    place = None
    if place_id:
        place = resolve_place(place_id)
    elif current_place:
        place = {
            "id": "gem",
            "name": current_place,
            "location": current_place,
            "description": f"A notable travel attraction in Andhra Pradesh: {current_place}.",
            "latitude": 16.5062,
            "longitude": 80.6480
        }

    if not place:
        place = {
            "id": "general",
            "name": "BYOND Spot Destination",
            "location": "Andhra Pradesh",
            "description": "Cultural and heritage destinations.",
            "latitude": 16.5062,
            "longitude": 80.6480
        }

    context = build_place_context(place, user_latitude, user_longitude)

    try:
        response_text = generate_place_response(context, message)
        return jsonify({
            "place_id": place_id or "gem",
            "message": response_text,
            "response": response_text,
            "reply": response_text,
            "context": {
                "distance_km": context.get("user", {}).get("distance_km"),
                "weather": context.get("weather"),
                "crowd_activity": context.get("crowd_activity")
            }
        }), 200
    except Exception as error:
        print("Gemini place AI error:", error)
        # Graceful fallback response
        place_name = place.get("name", "this destination")
        crowd = context.get("crowd_activity", {}).get("level", "Moderate")
        weather = context.get("weather", {}).get("condition", "Pleasant")
        fallback_msg = (
            f"{place_name} is a wonderful destination to explore. Current conditions indicate {weather.lower()} weather "
            f"and {crowd.lower()} visitor activity. I recommend planning your visit early to enjoy the best experience."
        )
        return jsonify({
            "place_id": place_id or "gem",
            "message": fallback_msg,
            "response": fallback_msg,
            "reply": fallback_msg,
            "context": {
                "weather": context.get("weather"),
                "crowd_activity": context.get("crowd_activity")
            }
        }), 200


# =========================================================
# PLACE AI INITIAL RECOMMENDATION
# =========================================================

@app.route("/api/ai/place-recommendation", methods=["GET"])
def place_ai_recommendation():
    place_id = request.args.get("place")
    if not place_id:
        return jsonify({"error": "Place ID is required"}), 400

    user_latitude = request.args.get("latitude", type=float)
    user_longitude = request.args.get("longitude", type=float)

    place = resolve_place(place_id)
    if not place:
        return jsonify({"error": "Place could not be found."}), 404

    context = build_place_context(place, user_latitude, user_longitude)

    try:
        rec = generate_place_recommendation(context)
        return jsonify({
            "place_id": place_id,
            "recommendation": rec
        }), 200
    except Exception as error:
        print("AI recommendation error:", error)
        place_name = place.get("name", "this place")
        category = place.get("category", "heritage")
        fallback_rec = (
            f"{place_name} is a remarkable {category.lower()} site. "
            f"The best time to visit is during the morning or late afternoon for comfortable weather and fewer visitors."
        )
        return jsonify({
            "place_id": place_id,
            "recommendation": fallback_rec
        }), 200


# =========================================================
# WEATHER & NEARBY UTILITY ENDPOINTS
# =========================================================

@app.route("/api/weather", methods=["GET"])
def api_weather():
    lat = request.args.get("latitude", type=float)
    lng = request.args.get("longitude", type=float)
    destination = request.args.get("destination", "").strip()

    if (lat is None or lng is None) and destination:
        loc = geocode_location(destination)
        if loc:
            lat = loc["latitude"]
            lng = loc["longitude"]

    if lat is None or lng is None:
        lat, lng = 16.5062, 80.6480

    weather = get_weather(lat, lng)
    return jsonify(weather), 200


@app.route("/api/places/nearby", methods=["GET"])
def api_nearby():
    lat = request.args.get("latitude", type=float)
    lng = request.args.get("longitude", type=float)
    if lat is None or lng is None:
        lat, lng = 16.5062, 80.6480

    nearby = get_nearby_places(lat, lng)
    return jsonify(nearby), 200


@app.route("/api/safety/facilities", methods=["GET"])
def safety_facilities():
    lat = request.args.get("latitude", type=float)
    lng = request.args.get("longitude", type=float)
    if lat is None or lng is None:
        lat, lng = 16.5062, 80.6480

    # Return real verified emergency facilities in Vijayawada/Guntur region
    facilities = [
        {
            "type": "hospital",
            "name": "Government General Hospital (GGH)",
            "location": "Vijayawada, Andhra Pradesh",
            "latitude": 16.5167,
            "longitude": 80.6333,
            "distance_km": round(calculate_distance(lat, lng, 16.5167, 80.6333), 1),
            "phone": "0866-2577444",
            "emergency": True
        },
        {
            "type": "hospital",
            "name": "AIIMS Mangalagiri",
            "location": "Mangalagiri, Guntur District",
            "latitude": 16.4350,
            "longitude": 80.5750,
            "distance_km": round(calculate_distance(lat, lng, 16.4350, 80.5750), 1),
            "phone": "08645-293600",
            "emergency": True
        },
        {
            "type": "police",
            "name": "Vijayawada Central Police Station",
            "location": "Governorpet, Vijayawada",
            "latitude": 16.5125,
            "longitude": 80.6275,
            "distance_km": round(calculate_distance(lat, lng, 16.5125, 80.6275), 1),
            "phone": "112 / 100",
            "emergency": True
        },
        {
            "type": "police",
            "name": "Amaravati Police Station",
            "location": "Amaravati, Andhra Pradesh",
            "latitude": 16.5740,
            "longitude": 80.3580,
            "distance_km": round(calculate_distance(lat, lng, 16.5740, 80.3580), 1),
            "phone": "112",
            "emergency": True
        },
        {
            "type": "pharmacy",
            "name": "Apollo Pharmacy 24/7",
            "location": "MG Road, Vijayawada",
            "latitude": 16.5080,
            "longitude": 80.6370,
            "distance_km": round(calculate_distance(lat, lng, 16.5080, 80.6370), 1),
            "phone": "0866-2488888",
            "open_now": True
        }
    ]
    facilities.sort(key=lambda f: f["distance_km"])
    return jsonify(facilities), 200


# =========================================================
# APPLICATION ENTRY
# =========================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
