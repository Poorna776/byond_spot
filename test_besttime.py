import sys
from services.crowd_service import get_live_crowd


def main():
    if len(sys.argv) < 3:
        print('Usage:')
        print('python test_besttime.py "Venue Name" "Venue Address"')
        return

    venue_name = sys.argv[1]
    venue_address = sys.argv[2]

    place = {
        "name": venue_name,
        "location": venue_address
    }

    print("=" * 60)
    print("BYOND Spot - BestTime Crowd Test")
    print("=" * 60)
    print(f"Venue   : {venue_name}")
    print(f"Address : {venue_address}")
    print("-" * 60)

    try:
        result = get_live_crowd(place)

        print("BestTime Response")
        print("-" * 60)

        for key, value in result.items():
            print(f"{key}: {value}")

        print("=" * 60)

    except Exception as error:
        print("ERROR:", error)
        print("=" * 60)


if __name__ == "__main__":
    main()