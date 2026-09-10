from app import app
from database import db, Hotel


hotels = [

    {
        "name": "Riverfront Grand Hotel",
        "location": "Riverside Road",
        "description": (
            "A comfortable city hotel located near the riverside, "
            "offering convenient access to nearby attractions and local experiences."
        ),
        "type": "Hotel",
        "rating": 4.6,
        "reviews": 1284,
        "price": 3200,
        "price_type": "mid",
        "activity": "moderate",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "image": "images/riverfront-grand-hotel.jpg"
    },

    {
        "name": "Heritage Residency",
        "location": "Heritage Area",
        "description": (
            "A premium heritage-style stay situated close to historic "
            "landmarks and cultural attractions."
        ),
        "type": "Heritage Stay",
        "rating": 4.8,
        "reviews": 842,
        "price": 4800,
        "price_type": "premium",
        "activity": "low",
        "latitude": 16.5728,
        "longitude": 80.3575,
        "image": "images/heritage-residency.jpg"
    },

    {
        "name": "Green View Inn",
        "location": "Green Park",
        "description": (
            "A budget-friendly stay offering a peaceful environment "
            "for travellers looking for comfortable accommodation."
        ),
        "type": "Hotel",
        "rating": 4.3,
        "reviews": 623,
        "price": 1800,
        "price_type": "budget",
        "activity": "low",
        "latitude": 16.5000,
        "longitude": 80.6200,
        "image": "images/green-view-inn.jpg"
    },

    {
        "name": "City Comfort Suites",
        "location": "City Centre",
        "description": (
            "A centrally located hotel offering convenient access to "
            "shopping, dining, transport and major city attractions."
        ),
        "type": "Hotel",
        "rating": 4.5,
        "reviews": 1532,
        "price": 2700,
        "price_type": "mid",
        "activity": "high",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "image": "images/city-comfort-suites.jpg"
    },

    {
        "name": "Lakeview Boutique Stay",
        "location": "Lakeside Road",
        "description": (
            "A boutique accommodation option offering a relaxed stay "
            "near scenic surroundings and local attractions."
        ),
        "type": "Boutique Stay",
        "rating": 4.7,
        "reviews": 492,
        "price": 5200,
        "price_type": "premium",
        "activity": "moderate",
        "latitude": 16.5146,
        "longitude": 80.6166,
        "image": "images/lakeview-boutique-stay.jpg"
    }

]


with app.app_context():

    for hotel_data in hotels:

        existing_hotel = Hotel.query.filter_by(
            name=hotel_data["name"]
        ).first()

        if existing_hotel:

            print(
                f"Already exists: {hotel_data['name']}"
            )

            continue

        hotel = Hotel(**hotel_data)

        db.session.add(hotel)

        print(
            f"Added: {hotel_data['name']}"
        )

    db.session.commit()

    print("\nHotel seeding completed successfully!")
    