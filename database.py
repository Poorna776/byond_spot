from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


# =========================
# USER MODEL
# =========================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f"<User {self.email}>"


# =========================
# PLACE MODEL
# =========================

class Place(db.Model):
    __tablename__ = "places"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(150),
        nullable=False
    )

    location = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=False
    )

    category = db.Column(
        db.String(100),
        nullable=False
    )

    latitude = db.Column(
        db.Float,
        nullable=False
    )

    longitude = db.Column(
        db.Float,
        nullable=False
    )

    rating = db.Column(
        db.Float,
        default=0.0
    )

    image = db.Column(
        db.String(300),
        nullable=True
    )

    def __repr__(self):
        return f"<Place {self.name}>"

    # =========================
# HOTEL MODEL
# =========================

class Hotel(db.Model):
    __tablename__ = "hotels"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(150),
        nullable=False
    )

    location = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    type = db.Column(
        db.String(100),
        nullable=False
    )

    rating = db.Column(
        db.Float,
        default=0.0
    )

    reviews = db.Column(
        db.Integer,
        default=0
    )

    price = db.Column(
        db.Integer,
        nullable=False
    )

    price_type = db.Column(
        db.String(50),
        nullable=False
    )

    activity = db.Column(
        db.String(50),
        nullable=False
    )

    latitude = db.Column(
        db.Float,
        nullable=False
    )

    longitude = db.Column(
        db.Float,
        nullable=False
    )

    image = db.Column(
        db.String(300),
        nullable=True
    )

    def __repr__(self):
        return f"<Hotel {self.name}>"

    # =========================
# RESTAURANT MODEL
# =========================

class Restaurant(db.Model):
    __tablename__ = "restaurants"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(150),
        nullable=False
    )

    location = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=True
    )

    cuisine = db.Column(
        db.String(100),
        nullable=False
    )

    cuisine_type = db.Column(
        db.String(100),
        nullable=False
    )

    rating = db.Column(
        db.Float,
        default=0.0
    )

    reviews = db.Column(
        db.Integer,
        default=0
    )

    price = db.Column(
        db.String(50),
        nullable=False
    )

    price_type = db.Column(
        db.String(50),
        nullable=False
    )

    activity = db.Column(
        db.String(50),
        nullable=False
    )

    latitude = db.Column(
        db.Float,
        nullable=False
    )

    longitude = db.Column(
        db.Float,
        nullable=False
    )

    image = db.Column(
        db.String(300),
        nullable=True
    )

    def __repr__(self):
        return f"<Restaurant {self.name}>"

    # =========================
# TRIP MODEL
# =========================

class Trip(db.Model):
    __tablename__ = "trips"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    destination_id = db.Column(
        db.Integer,
        nullable=True
    )

    destination_name = db.Column(
        db.String(200),
        nullable=False
    )

    start_date = db.Column(
        db.String(20),
        nullable=False
    )

    end_date = db.Column(
        db.String(20),
        nullable=False
    )

    duration_days = db.Column(
        db.Integer,
        nullable=False
    )

    travellers = db.Column(
        db.Integer,
        nullable=False
    )

    budget = db.Column(
        db.Float,
        nullable=False
    )

    interests = db.Column(
        db.Text,
        nullable=True
    )

    travel_style = db.Column(
        db.String(50),
        nullable=False
    )

    transport = db.Column(
        db.String(100),
        nullable=False
    )

    # AI-generated itinerary
    itinerary = db.Column(
        db.Text,
        nullable=True
    )

    # Original AI itinerary.
    # This is preserved even if the user later modifies the plan.
    original_itinerary = db.Column(
        db.Text,
        nullable=True
    )

    status = db.Column(
        db.String(30),
        nullable=False,
        default="planned"
    )

    current_day = db.Column(
        db.Integer,
        nullable=False,
        default=1
    )

    total_spent = db.Column(
        db.Float,
        nullable=False,
        default=0
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    started_at = db.Column(
        db.DateTime,
        nullable=True
    )

    completed_at = db.Column(
        db.DateTime,
        nullable=True
    )

    def __repr__(self):
        return f"<Trip {self.id}: {self.destination_name}>"