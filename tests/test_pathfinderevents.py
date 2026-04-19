import json
from http import HTTPStatus
from unittest.mock import ANY

from conftest import AUTH_HEADERS

from pathfinderevents import app, from_pathfinder_request_data

_WEBHOOK_ENDPOINT = "/webhook"
_CONTENT_TYPE_TEXT = "text/plain; charset=utf-8"


async def test_from_pathfinder_request_data():
    ce = from_pathfinder_request_data("event=OnAir&channel=Klangbecken")
    assert ce.get_type() == "ch.rabe.api.events.pathfinder.v0alpha1.OnAir"
    assert ce.get_subject() == "Klangbecken"
    assert ce.get_attributes()["datacontenttype"] == "text/plain"


async def test_webhook(mock_producer):
    async with app.test_client() as client:
        resp = await client.post(
            _WEBHOOK_ENDPOINT,
            data="event=OnAir&channel=Klangbecken",
            headers={"Content-Type": _CONTENT_TYPE_TEXT, **AUTH_HEADERS},
        )
    assert resp.status_code == HTTPStatus.OK
    mock_producer.send.assert_called_once_with(
        "test",
        key="ch.rabe.api.events.pathfinder.v0alpha1.OnAir.Klangbecken",
        value=ANY,
        headers=[("content-type", b"application/cloudevents+json")],
    )
    value = json.loads(mock_producer.send.call_args.kwargs["value"])
    assert value["data"] == "Klangbecken"
    assert "partitionid" not in value
    assert (
        value["source"] == "https://github.com/radiorabe/pathfinder-cloudevents-service"
    )
    assert value["subject"] == "Klangbecken"


async def test_webhook_unauthorized():
    async with app.test_client() as client:
        resp = await client.post(
            _WEBHOOK_ENDPOINT,
            data="event=OnAir&channel=Klangbecken",
            headers={"Content-Type": _CONTENT_TYPE_TEXT},
        )
    assert resp.status_code == HTTPStatus.UNAUTHORIZED
    assert resp.headers.get("WWW-Authenticate") is not None


async def test_stop_producer(mock_producer):
    async with app.test_app():
        pass
    mock_producer.flush.assert_called()
    mock_producer.stop.assert_called()
