"""GET /api/places/: city suggestions for the form's From and To fields (fake TomTom)."""

import re

import pytest

SEARCH = re.compile(r"https://api\.tomtom\.com/search/2/search/.+")


def city(name: str, region: str) -> dict:
    return {"address": {"municipality": name, "countrySubdivision": region}}


def test_places(client, http):
    http.get(SEARCH, json={"results": [city("Dallas", "TX"), city("Dale", "VA")]})

    response = client.get("/api/places/", {"q": "Dal"})

    assert response.status_code == 200
    assert response.json() == {"places": [{"name": "Dallas, TX"}, {"name": "Dale, VA"}]}


@pytest.mark.parametrize(
    ("query", "message"),
    [
        (None, "This field is required."),
        ("   ", "This field may not be blank."),
        ("Da", "Type at least 3 letters or digits."),
        ("D a ", "Type at least 3 letters or digits."),
        ("...", "Type at least 3 letters or digits."),  # TomTom would answer with random cities
        ("x" * 201, "Ensure this field has no more than 200 characters."),
    ],
)
def test_places_need_three_letters_or_digits(client, http, query, message):
    response = client.get("/api/places/", {} if query is None else {"q": query})

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_input", "message": message, "fields": {"q": message}}
    }
    assert len(http.calls) == 0  # TomTom isn't asked


def test_places_report_upstream_failures(client, http):
    http.get(SEARCH, status=503, json={"detailedError": {"code": "Unavailable", "message": "down"}})

    response = client.get("/api/places/", {"q": "Dal"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "routing_unavailable"


def test_places_only_answer_get(client):
    response = client.post("/api/places/", {"q": "Dal"})

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
