from app import app
from database import db, Restaurant


restaurants = [

    {
        "name": "Andhra Spice Kitchen",
        "location": "City Centre",
        "description": (
            "A popular local restaurant serving authentic Andhra and "
            "South Indian dishes with traditional flavours."
        ),
        "cuisine": "South Indian",
        "cuisine_type": "south-indian",
        "rating": 4.7,
        "reviews": 1842,
        "price": "₹₹",
        "price_type": "budget",
        "activity": "moderate",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "image": "images/andhra-spice-kitchen.jpg"
    },

    {
        "name": "Heritage Dining House",
        "location": "Heritage Area",
        "description": (
            "A premium dining destination offering North Indian cuisine "
            "in a comfortable heritage-inspired setting."
        ),
        "cuisine": "North Indian",
        "cuisine_type": "north-indian",
        "rating": 4.8,
        "reviews": 936,
        "price": "₹₹₹",
        "price_type": "premium",
        "activity": "low",
        "latitude": 16.5728,
        "longitude": 80.3575,
        "image": "images/heritage-dining-house.jpg"
    },

    {
        "name": "Riverside Café",
        "location": "Riverside",
        "description": (
            "A relaxed café near the riverside offering beverages, "
            "light meals and a peaceful atmosphere."
        ),
        "cuisine": "Café",
        "cuisine_type": "cafe",
        "rating": 4.4,
        "reviews": 721,
        "price": "₹₹",
        "price_type": "mid",
        "activity": "low",
        "latitude": 16.5146,
        "longitude": 80.6166,
        "image": "images/riverside-cafe.jpg"
    },

    {
        "name": "The Local Table",
        "location": "Market Area",
        "description": (
            "A lively multi-cuisine restaurant located near the local "
            "market, offering a variety of popular dishes."
        ),
        "cuisine": "Multi-cuisine",
        "cuisine_type": "multi",
        "rating": 4.5,
        "reviews": 1268,
        "price": "₹₹",
        "price_type": "mid",
        "activity": "high",
        "latitude": 16.5000,
        "longitude": 80.6200,
        "image": "images/the-local-table.jpg"
    },

    {
        "name": "Garden View Restaurant",
        "location": "Green Park",
        "description": (
            "A comfortable multi-cuisine restaurant surrounded by "
            "greenery, suitable for relaxed meals."
        ),
        "cuisine": "Multi-cuisine",
        "cuisine_type": "multi",
        "rating": 4.6,
        "reviews": 514,
        "price": "₹₹₹",
        "price_type": "premium",
        "activity": "moderate",
        "latitude": 16.5000,
        "longitude": 80.6200,
        "image": "images/garden-view-restaurant.jpg"
    }

]


with app.app_context():

    for restaurant_data in restaurants:

        existing_restaurant = Restaurant.query.filter_by(
            name=restaurant_data["name"]
        ).first()

        if existing_restaurant:
            print(
                f"Already exists: {restaurant_data['name']}"
            )

            continue

        restaurant = Restaurant(
            **restaurant_data
        )

        db.session.add(restaurant)

        print(
            f"Added: {restaurant_data['name']}"
        )

    db.session.commit()

    print("\nRestaurant seeding completed successfully!")