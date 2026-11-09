"""Delivery lookup contract without sending any coordinates to Google."""
from collections import OrderedDict
from io import BytesIO
import json
from urllib.parse import parse_qs, urlsplit

from api import geocoding
from test_workflows import login

PATH = '/api/delivery/reverse-geocode'
COORDINATES = {'lat': 10.7769, 'lng': 106.7009}


def test_lookup_requires_a_customer_and_reports_missing_configuration(api, monkeypatch):
    monkeypatch.setattr(geocoding, 'GOOGLE_MAPS_API_KEY', '')
    assert api.post(PATH, json=COORDINATES).status_code == 401
    login(api, 'admin')
    assert api.post(PATH, json=COORDINATES).status_code == 403
    login(api)
    response = api.post(PATH, json=COORDINATES)
    assert response.status_code == 503
    assert 'manually' in response.json()['detail']


def test_google_reverse_lookup_returns_a_street_address(api, monkeypatch):
    monkeypatch.setattr(geocoding, 'GOOGLE_MAPS_API_KEY', 'test-maps-key')
    monkeypatch.setattr(geocoding, 'lookup_times', OrderedDict())

    def provider(request, timeout):
        parts = urlsplit(request.full_url)
        assert parts.netloc == 'geocode.googleapis.com'
        assert parts.path == '/v4/geocode/location'
        query = parse_qs(parts.query)
        assert query == {'location.latitude': ['10.7769'], 'location.longitude': ['106.7009'], 'languageCode': ['vi']}
        assert dict((key.lower(), value) for key, value in request.header_items())['x-goog-api-key'] == 'test-maps-key'
        return BytesIO(json.dumps({'results': [
            {'formattedAddress': 'Hồ Chí Minh', 'types': ['locality']},
            {'formattedAddress': '19 Nguyễn Huệ, Hồ Chí Minh', 'types': ['street_address']},
        ]}).encode())

    monkeypatch.setattr(geocoding, 'urlopen', provider)
    login(api)
    assert api.post(PATH, json={'lat': 91, 'lng': 106}).status_code == 422
    response = api.post(PATH, json=COORDINATES)
    assert response.status_code == 200
    assert response.json() == {'address': '19 Nguyễn Huệ, Hồ Chí Minh', 'source': 'google_maps'}
    assert api.post(PATH, json=COORDINATES).status_code == 429


def test_lookup_without_a_street_result_allows_manual_entry(api, monkeypatch):
    monkeypatch.setattr(geocoding, 'GOOGLE_MAPS_API_KEY', 'test-maps-key')
    monkeypatch.setattr(geocoding, 'lookup_times', OrderedDict())
    monkeypatch.setattr(geocoding, 'urlopen', lambda *args, **kwargs: BytesIO(b'{"results": [{"formattedAddress": "City", "types": ["locality"]}]}'))
    login(api)
    response = api.post(PATH, json=COORDINATES)
    assert response.status_code == 404
    assert 'manually' in response.json()['detail']


def test_provider_failure_does_not_expose_provider_details(api, monkeypatch):
    monkeypatch.setattr(geocoding, 'GOOGLE_MAPS_API_KEY', 'test-maps-key')
    monkeypatch.setattr(geocoding, 'lookup_times', OrderedDict())

    def unavailable(*args, **kwargs):
        raise TimeoutError('test-maps-key / raw upstream error')

    monkeypatch.setattr(geocoding, 'urlopen', unavailable)
    login(api)
    response = api.post(PATH, json=COORDINATES)
    assert response.status_code == 503
    assert 'manually' in response.json()['detail']
    assert 'test-maps-key' not in response.text
