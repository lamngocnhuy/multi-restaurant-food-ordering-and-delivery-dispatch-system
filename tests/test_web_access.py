"""Browser entry points keep customer ordering behind the sign-in page."""
import pytest

from test_workflows import ADDRESS, login, ok, place


def assert_standalone_sign_in(response):
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert response.headers['cache-control'] == 'no-store'
    html = response.text
    assert 'id="auth-form"' in html
    assert 'name="email"' in html and 'name="password"' in html
    assert '/static/auth.js?v=' in html and '/static/style.css?v=' in html
    assert '/static/app.js' not in html
    assert 'data-customer-only' not in html and 'id="basket-panel"' not in html


@pytest.mark.parametrize('path', ['/', '/sign-in', '/order', '/orders', '/reviews', '/admin'])
def test_signed_out_pages_only_render_standalone_sign_in(api, path):
    assert_standalone_sign_in(api.get(path, follow_redirects=False))


def test_customer_order_entry_uses_the_signed_in_catalog(api):
    login(api)
    redirect = api.get('/sign-in', follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers['location'] == '/order'

    page = api.get(redirect.headers['location'])
    assert page.status_code == 200
    assert page.headers['cache-control'] == 'no-store'
    assert '/static/app.js?v=' in page.text and '/static/style.css?v=' in page.text
    assert 'id="basket-panel"' in page.text and '/static/auth.js' not in page.text

    restaurants = ok(api.get('/api/restaurants'))['restaurants']
    restaurant = next(r for r in restaurants if r['accepting_orders'])
    menu = ok(api.get(f"/api/restaurants/{restaurant['id']}"))['menu']
    dish = next(item for item in menu if item['available'])
    cart = ok(api.post('/api/cart/items', json={'menu_item_id': dish['id']}))
    assert cart['item_count'] == 1

    quote = ok(api.post('/api/cart/quote', json=ADDRESS))
    order = place(api)['order']
    assert order['total'] == quote['total']
    assert order['suborders'][0]['restaurant_id'] == restaurant['id']

    ok(api.post('/api/auth/logout'))
    assert_standalone_sign_in(api.get('/order', follow_redirects=False))


@pytest.mark.parametrize('role', ['restaurant', 'driver', 'admin'])
def test_staff_are_sent_to_their_workspaces_from_customer_order_entry(api, role):
    login(api, role)
    for path in ('/sign-in', '/order'):
        response = api.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers['location'] == f'/{role}'
