import dataclasses
import re
from fastapi.testclient import TestClient
from app import admin, db, game
from app.main import app


def test_admin_creation_and_invited_reader(monkeypatch):
    monkeypatch.setattr(admin, 'settings', dataclasses.replace(admin.settings, admin_key='test-long-admin-secret'))
    monkeypatch.setattr(admin, '_tries', {})
    visitor = TestClient(app)
    assert visitor.post('/circles', data={'name': 'No'}).status_code == 403
    assert 'action="/circles"' not in visitor.get('/').text
    owner = TestClient(app)
    owner.post('/admin', data={'key': 'test-long-admin-secret'})
    assert owner.post('/circles', data={'name': 'No token'}).status_code == 403
    token = re.search(r'name="csrf_token" value="([^"]+)"', owner.get('/').text)[1]
    res = owner.post('/circles', data={'name': 'Private', 'csrf_token': token}, follow_redirects=False)
    assert res.status_code == 303
    path = res.headers['location'].split('?')[0]
    circle = game.get_circle(path.split('/')[-1])
    db.save_story(circle['id'], game.today(), 'Shared story', 'Friends together', 'Keep going', 1, 'placeholder', 'classic', [])
    assert visitor.get(path).status_code == 404
    page = visitor.get(path + '?invite=' + circle['invite_token'])
    assert 'Shared story' in page.text and 'Add my answers' in page.text
    assert 'name="hope"' in visitor.get(path + '?answer=1').text
