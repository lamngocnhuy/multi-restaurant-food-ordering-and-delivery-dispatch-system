"""Isolated integration tests; set TEST_DATABASE_URL for real PostgreSQL checks."""
import os
from pathlib import Path
import tempfile
import pytest
from sqlalchemy import make_url, event
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# Never permit this suite to reset an application database accidentally.
TEST_URL = os.getenv('TEST_DATABASE_URL', 'sqlite:///' + str(Path(tempfile.mkdtemp(prefix='gather-tests-')) / 'test.sqlite3'))
url = make_url(TEST_URL)
if url.get_backend_name() != 'sqlite' and not (url.database or '').endswith('_test'):
    raise RuntimeError('TEST_DATABASE_URL database name must end in _test.')
os.environ.update(DATABASE_URL=TEST_URL, SEED_DEMO='true', ENABLE_SCHEDULER='false',
                  APP_ENV='development', COOKIE_SECURE='false', SECURE_COOKIES='false',
                  DEMO_PASSWORD='Demo123!', TRUSTED_HOSTS='localhost,127.0.0.1,testserver')

from main import app
from database.connection import Base, engine, get_db

if engine.dialect.name == 'sqlite':
    # Python sqlite legacy transaction control otherwise releases savepoints before
    # an outer BEGIN, leaking state between acceptance tests.
    @event.listens_for(engine, 'connect')
    def sqlite_transactions(connection, _):
        connection.isolation_level = None
    @event.listens_for(engine, 'begin')
    def sqlite_begin(connection):
        connection.exec_driver_sql('BEGIN')

@pytest.fixture(scope='session', autouse=True)
def application():
    Base.metadata.drop_all(engine)
    with TestClient(app):
        yield app
    Base.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def db(application):
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode='create_savepoint', expire_on_commit=False)
    def override_db():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
    app.dependency_overrides[get_db] = override_db
    yield session
    app.dependency_overrides.clear()
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def api(db):
    client = TestClient(app)
    yield client
    client.close()
