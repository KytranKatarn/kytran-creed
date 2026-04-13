def test_get_overall_badge_svg(client):
    resp = client.get("/api/v1/badge/overall")
    assert resp.status_code == 200
    assert resp.content_type.startswith("image/svg+xml")
    assert b"<svg" in resp.data
    assert b"C.R.E.E.D." in resp.data


def test_get_category_badge(client):
    resp = client.get("/api/v1/badge/safety")
    assert resp.status_code == 200
    assert b"<svg" in resp.data


def test_invalid_badge_type_returns_404(client):
    resp = client.get("/api/v1/badge/nonexistent")
    assert resp.status_code == 404
