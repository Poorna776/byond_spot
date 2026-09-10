from app import app
from database import db, Place


places = [
    {
        "name": "Undavalli Caves",
        "location": "Vijayawada, Andhra Pradesh",
        "description": (
            "Ancient rock-cut caves known for their impressive "
            "architecture, sculptures and historic significance."
        ),
        "category": "Heritage",
        "latitude": 16.4963,
        "longitude": 80.5894,
        "rating": 4.8,
        "image": "images/undavalli-caves.jpg"
    },

    {
        "name": "Amaravati Historical Site",
        "location": "Amaravati, Andhra Pradesh",
        "description": (
            "A historic destination associated with Buddhist heritage, "
            "ancient monuments and the Amaravati archaeological tradition."
        ),
        "category": "Culture",
        "latitude": 16.5728,
        "longitude": 80.3575,
        "rating": 4.7,
        "image": "images/amaravati.jpg"
    },

    {
        "name": "Kondaveedu Fort",
        "location": "Guntur, Andhra Pradesh",
        "description": (
            "A historic hilltop fort surrounded by scenic landscapes "
            "and known for its connection to the Reddy dynasty."
        ),
        "category": "Heritage",
        "latitude": 16.4570,
        "longitude": 80.2500,
        "rating": 4.6,
        "image": "images/kondaveedu-fort.jpg"
    },

    {
        "name": "Kondapalli",
        "location": "Vijayawada, Andhra Pradesh",
        "description": (
            "A destination known for Kondapalli Fort, scenic surroundings "
            "and the traditional Kondapalli wooden handicrafts."
        ),
        "category": "Culture",
        "latitude": 16.6170,
        "longitude": 80.5410,
        "rating": 4.6,
        "image": "images/kondapalli.jpg"
    },

    {
        "name": "Bhavani Island",
        "location": "Vijayawada, Andhra Pradesh",
        "description": (
            "A scenic river island on the Krishna River offering "
            "relaxing surroundings and recreational experiences."
        ),
        "category": "Nature",
        "latitude": 16.5146,
        "longitude": 80.6166,
        "rating": 4.5,
        "image": "images/bhavani-island.jpg"
    },

    {
        "name": "Mangalagiri",
        "location": "Guntur, Andhra Pradesh",
        "description": (
            "A historic town known for its hill, temple heritage "
            "and traditional handloom and textile culture."
        ),
        "category": "Culture",
        "latitude": 16.4308,
        "longitude": 80.5685,
        "rating": 4.6,
        "image": "images/mangalagiri.jpg"
    }
]


with app.app_context():

    for place_data in places:

        existing_place = Place.query.filter_by(
            name=place_data["name"]
        ).first()

        if existing_place:
            print(
                f"Already exists: {place_data['name']}"
            )
            continue

        place = Place(**place_data)

        db.session.add(place)

        print(
            f"Added: {place_data['name']}"
        )

    db.session.commit()

    print("\nPlace seeding completed successfully!")