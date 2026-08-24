from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import strava_collections.activity as activity_module
import strava_collections.collection as collection_module
from strava_collections.collection import StravaCollection
from strava_collections.main import (
    InputValidationError,
    parse_activity_inputs,
    parse_single_strava_id,
)


def test_collection_construction_does_not_load_activities(monkeypatch):
    activity = Mock()
    activity.activity = SimpleNamespace(
        distance=0.0,
        total_elevation_gain=0.0,
        moving_time=0.0,
        name="Trip",
    )
    constructor = Mock(return_value=activity)
    monkeypatch.setattr(collection_module, "StravaActivity", constructor)

    collection = StravaCollection("Trip", [{"strava_id": (123, False)}])

    constructor.assert_not_called()
    assert collection.activity_ids == []

    collection.load_activities()
    constructor.assert_called_once_with(
        123, flip=False, force_update=False, verbose=False
    )


def test_parse_activity_inputs_does_not_mutate_input():
    original = {"id": "123", "routeGpxFile": "route.gpx"}

    parsed = parse_activity_inputs([original])

    assert original == {"id": "123", "routeGpxFile": "route.gpx"}
    assert parsed == [
        {"id": "123", "routeGpxFile": "route.gpx", "strava_id": (123, False)}
    ]


@pytest.mark.parametrize("value", ["", "abc", 0, -1, True])
def test_parse_single_strava_id_rejects_invalid_values(value):
    with pytest.raises(InputValidationError):
        parse_single_strava_id(value)


def test_photo_request_has_timeout_and_raises_domain_error(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = activity_module.requests.HTTPError(
        "bad gateway"
    )
    request = Mock(return_value=response)
    monkeypatch.setattr(activity_module.requests, "get", request)

    with pytest.raises(activity_module.StravaAPIError, match="activity 123"):
        activity_module.get_activity_photos_from_web(123, "token")

    request.assert_called_once_with(
        "https://www.strava.com/api/v3/activities/123/photos?size=5000",
        headers={"Authorization": "Bearer token"},
        timeout=15.0,
    )
