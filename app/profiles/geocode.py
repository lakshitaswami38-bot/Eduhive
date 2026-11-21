import time

from geopy.exc import GeopyError
from geopy.geocoders import Nominatim

# India's rough bounding box. Anything outside it is almost certainly a wrong match.
LAT_RANGE = (6.0, 37.5)
LNG_RANGE = (68.0, 97.5)


def in_india(lat, lng):
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]


def geocode_school(address, city, state, pincode):
    """Find a school's coordinates with OpenStreetMap's Nominatim (free).

    Returns (latitude, longitude, source) or None.
    source is "address" for a street-level match, "pincode" for an approximate one.
    Nominatim allows about 1 request per second, so we wait between tries.
    """
    geolocator = Nominatim(user_agent="EduHive-college-project", timeout=5)
    attempts = [
        ("address", f"{address}, {city}, {state} {pincode}, India"),
        ("pincode", f"{pincode}, India"),
    ]
    try:
        for index, (source, query) in enumerate(attempts):
            if index:
                time.sleep(1)
            place = geolocator.geocode(query, country_codes="in")
            if place and in_india(place.latitude, place.longitude):
                return place.latitude, place.longitude, source
    except (GeopyError, OSError):
        return None
    return None