"""The retired lookup no longer accepts customer coordinates."""
from test_workflows import login


def test_reverse_geocoding_endpoint_is_not_available(api):
    login(api)
    response = api.post('/api/delivery/reverse-geocode', json={'lat': 10.7769, 'lng': 106.7009})
    assert response.status_code == 404
