import pytest
from sqlalchemy import create_engine


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    try:
        yield engine
    finally:
        engine.dispose()
