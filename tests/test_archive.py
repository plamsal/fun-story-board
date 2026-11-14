import dataclasses
import re
from fastapi.testclient import TestClient
from app import admin, db, game
from app.main import app


def test_archive_behind_https_proxy(monkeypatch):
    monkeypatch.setattr(admin, 'settings', dataclasses.replace(admin.settings, admin_key='long-test-admin-key'))
    monkeypatch.setattr(admin, '_tries', {})
    circle = game.create_circle('Archive test', 3)
    url = f"/admin/circles/{circle['id']}/archive"
    browser = TestClient(app, base_url='http://example.test')
    assert browser.post(url, follow_redirects=False).status_code == 303
    browser.post('/admin', data={'key': 'long-test-admin-key'})
    assert browser.post(url, data={'archived': '1'}).status_code == 403
    token = re.search(r'name="csrf_token" value="([^"]+)"', browser.get('/admin').text)[1]
    for value in ('1', '0'):
        response = browser.post(url, headers={'origin': 'https://example.test'},
                                data={'archived': value, 'csrf_token': token}, follow_redirects=False)
        assert response.status_code == 303
        assert db.get_circle(circle['id'])['archived'] == int(value)
