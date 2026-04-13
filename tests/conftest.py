import pytest
import tempfile
import os


@pytest.fixture
def app():
    from kytran_creed.app import create_app
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    app = create_app({"TESTING": True, "DB_PATH": db_path, "SECRET_KEY": "test"})
    yield app
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()
