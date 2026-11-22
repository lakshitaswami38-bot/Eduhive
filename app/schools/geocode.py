import math
import time

from geopy.exc import GeopyError
from geopy.geocoders import Nominatim

# India's rough bounding box. Anything outside it is almost certainly a wrong match.
LAT_RANGE = (6.0, 37.5)
LNG_RANGE = (68.0, 97.5)


def in_india(lat, lng):
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]


def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the great-circle distance between two points in km."""
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 6371.0  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)


def geocode_pincode(pincode):
    """Geocode an Indian pincode to (latitude, longitude) or None."""
    geolocator = Nominatim(user_agent="EduHive-college-project", timeout=5)
    try:
        place = geolocator.geocode(f"{pincode}, India", country_codes="in")
        if place and in_india(place.latitude, place.longitude):
            return place.latitude, place.longitude
    except (GeopyError, OSError):
        return None
    return None


def geocode_place(query):
    """Geocode a city, area, locality or landmark to (latitude, longitude) or None."""
    if not query:
        return None
    geolocator = Nominatim(user_agent="EduHive-college-project", timeout=5)
    try:
        place = geolocator.geocode(f"{query}, India", country_codes="in")
        if place and in_india(place.latitude, place.longitude):
            return place.latitude, place.longitude
    except (GeopyError, OSError):
        return None
    return None


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