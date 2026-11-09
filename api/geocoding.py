"""Resolve a customer-requested device location without exposing the Maps key."""
import json
from collections import OrderedDict
from threading import Lock
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException

from api.routes import customer
from forms.schemas import Location
from models.entities import User
from properties.config import GOOGLE_MAPS_API_KEY

router = APIRouter(prefix='/api/delivery', tags=['delivery'])
GOOGLE_GEOCODE_URL = 'https://geocode.googleapis.com/v4/geocode/location'
ADDRESS_TYPES = {'street_address', 'premise', 'subpremise', 'route', 'intersection', 'establishment', 'point_of_interest'}
lookup_times: OrderedDict[str, float] = OrderedDict()
lookup_lock = Lock()


@router.post('/reverse-geocode')
def reverse_geocode(location: Location, user: User = Depends(customer)):
    if not GOOGLE_MAPS_API_KEY:
        raise HTTPException(503, 'Google Maps address lookup is not configured. Enter your street address manually.')

    with lookup_lock:
        now = monotonic()
        while lookup_times and now - next(iter(lookup_times.values())) >= 3:
            lookup_times.popitem(last=False)
        if user.id in lookup_times:
            raise HTTPException(429, 'Please wait a few seconds before looking up your location again.')
        lookup_times[user.id] = now

    query = urlencode({'location.latitude': location.lat, 'location.longitude': location.lng, 'languageCode': 'vi'})
    request = Request(f'{GOOGLE_GEOCODE_URL}?{query}', headers={
        'X-Goog-Api-Key': GOOGLE_MAPS_API_KEY,
        'X-Goog-FieldMask': 'results.formattedAddress,results.types',
    })
    try:
        # Keep the provider response, API key, and precise location out of application logs.
        with urlopen(request, timeout=5) as response:
            result = json.load(response)
    except (OSError, ValueError):
        raise HTTPException(503, 'Google Maps could not look up this location. Try again or enter your street address manually.') from None

    # Do not autofill a city, district, or Plus Code as if it were a street address.
    matches = result.get('results', []) if isinstance(result, dict) else None
    if not isinstance(matches, list):
        raise HTTPException(503, 'Google Maps returned an unexpected response. Enter your street address manually.')
    for match in matches:
        if not isinstance(match, dict):
            continue
        address = match.get('formattedAddress')
        types = match.get('types')
        if isinstance(address, str) and isinstance(types, list):
            address = address.strip()
            if 5 <= len(address) <= 300 and ADDRESS_TYPES.intersection(t for t in types if isinstance(t, str)):
                return {'address': address, 'source': 'google_maps'}
    raise HTTPException(404, 'Google Maps did not find a street address here. Enter the delivery address manually.')
