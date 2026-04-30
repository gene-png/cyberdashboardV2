import pytest
from app import create_app
from app.config import TestingConfig
from app.extensions import db as _db
from app.models import User, Assessment


@pytest.fixture(scope="session")
def app():
    application = create_app(TestingConfig)
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()
        _db.create_all()


@pytest.fixture(scope="function")
def client(app, db):
    return app.test_client()


@pytest.fixture(scope="function")
def admin_user(db):
    user = User(username="admin", role="admin")
    user.set_password("adminpass")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture(scope="function")
def sample_assessment(db):
    assessment = Assessment(
        customer_org="Test Org",
        framework="dod_zt",
        variant="zt_only",
        status="draft",
    )
    db.session.add(assessment)
    db.session.flush()

    customer = User(
        username="testcustomer",
        role="customer",
        assessment_id=assessment.id,
    )
    customer.set_password("custpass")
    db.session.add(customer)
    db.session.commit()
    return assessment


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
