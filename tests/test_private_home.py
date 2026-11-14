import dataclasses
from fastapi.testclient import TestClient
from app import admin, game
from app.main import app


def test_home_never_lists_circles_and_invitation_stays_scoped(monkeypatch):
    circle = game.create_circle('Hidden family name', 3)
    other = game.create_circle('Hidden other name', 3)
    client = TestClient(app)
    path = f"/c/{circle['id']}"
    assert client.get(path + '?invite=' + circle['invite_token']).status_code == 200
    assert client.get(f"/c/{other['id']}").status_code == 404
    for suffix in ('/archive', '/status', '/card.png'):
        assert client.get(f"/c/{other['id']}" + suffix).status_code == 404
    page = client.get('/').text
    assert 'Your circles' not in page
    assert circle['name'] not in page and circle['id'] not in page
    assert other['name'] not in page
    monkeypatch.setattr(admin, 'settings', dataclasses.replace(admin.settings, admin_key='private-home-admin-key'))
    monkeypatch.setattr(admin, '_tries', {})
    client.post('/admin', data={'key': 'private-home-admin-key'})
    assert circle['name'] not in client.get('/').text
    assert circle['name'] in client.get('/admin').text
