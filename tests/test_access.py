"""Access checks use independent browsers with no automatic invitation helper."""
import dataclasses

from fastapi.testclient import TestClient

from app import admin, db, game
from app.main import app


def test_private_circle_boundaries(monkeypatch):
    owner, friend, outsider = (TestClient(app) for _ in range(3))
    res = owner.post('/circles', data={'name': 'Private circle', 'people_limit': '3'}, follow_redirects=False)
    path = res.headers['location'].split('?')[0]
    circle = game.get_circle(path.split('/')[-1])
    other = game.create_circle('Another private circle', 3)
    assert owner.get(path).status_code == 200
    for suffix in ('', '/status', '/archive', '/d/2020-01-01', '/card.png'):
        assert outsider.get(path + suffix).status_code == 404
    assert outsider.post(path + '/words', data={}).status_code == 404
    assert outsider.get(path + '?invite=wrong').status_code == 404
    assert outsider.get(path + '?invite=雪').status_code == 404
    assert friend.get(path + '?invite=' + circle['invite_token']).status_code == 200
    assert friend.get(path).status_code == 200
    assert friend.get(f"/c/{other['id']}").status_code == 404
    outsider.cookies.set('sb_circles', circle['id'])
    assert 'Private circle' not in outsider.get('/').text
    assert friend.get(path + '/status').headers['cache-control'] == 'no-store'
    assert db.is_circle_member(circle['id'], friend.cookies.get('sb_player'))


def test_admin_can_review_without_contributing(monkeypatch):
    monkeypatch.setattr(admin, 'settings', dataclasses.replace(admin.settings, admin_key='test-secret-long-enough'))
    monkeypatch.setattr(admin, '_tries', {})
    circle = game.create_circle('Admin review', 3)
    player = game.new_player_id()
    game.add_words(circle, player, {'name': 'Asha', 'hope': 'travel', 'weight': 'doubt', 'strength': 'mom'})
    db.save_story(circle['id'], game.today(), 'Review title', 'A story', 'Keep going', 1, 'placeholder', 'classic', [])
    browser = TestClient(app)
    assert 'type="password"' in browser.get('/admin').text
    assert browser.get('/admin/answers.csv').status_code == 404
    assert browser.post('/admin', data={'key': 'wrong'}).status_code == 403
    assert browser.post('/admin', data={'key': 'test-secret-long-enough'}).status_code == 200
    page = browser.get(f"/c/{circle['id']}")
    assert 'Review title' in page.text
    assert 'travel' in browser.get('/admin').text
    assert browser.get('/admin/answers.csv').status_code == 200
    browser.post('/admin/logout')
    assert 'type="password"' in browser.get('/admin').text
    assert browser.get(f"/c/{circle['id']}").status_code == 404


def test_existing_contributors_keep_membership_on_upgrade():
    circle = game.create_circle('Existing circle', 3)
    player = game.new_player_id()
    db.insert_contribution(circle['id'], '2020-01-01', player, 'Friend', {'hope': 'sun'})
    db._all("UPDATE circles SET invite_token = '' WHERE id = ?", circle['id'])
    db.create_tables()
    token = db.get_circle(circle['id'])['invite_token']
    assert len(token) >= 32
    assert db.is_circle_member(circle['id'], player)
    db.create_tables()
    assert db.get_circle(circle['id'])['invite_token'] == token
    browser = TestClient(app)
    browser.cookies.set('sb_player', player)
    assert browser.get(f"/c/{circle['id']}").status_code == 200
