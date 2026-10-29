import pytest
import responses
from django.core.cache import cache

from .fakes import FakeServices


@pytest.fixture(autouse=True)
def empty_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def http():
    """Blocks real HTTP in every test (an unregistered request fails); register expected ones here."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def services(http):
    """Fake TomTom and Open-Meteo for Dallas -> Denver."""
    return FakeServices(http)
