import json
from unittest.mock import ANY, patch

from conftest import AuthenticatedClient

from pathfinderevents import ApiServer, app

_WEBHOOK_ENDPOINT = "/webhook"
_CONTENT_TYPE_TEXT = "text/plain; charset=utf-8"


@patch("pathfinderevents.sys.exit")
@patch("pathfinderevents.ApiServer")
@patch("pathfinderevents.KafkaProducer")
def test_app(mock_producer, mock_api, mock_sys_exit):  # noqa: ARG001
    mock_producer.return_value = mock_producer
    app(
        api=mock_api,
        bootstrap_servers="server:9092",
        security_protocol="SSL",
        tls_cafile=None,
        tls_certfile=None,
        tls_keyfile=None,
    )
    mock_api.set_producer.assert_called_once_with(mock_producer)
    mock_api.run_server.assert_called_once()
    mock_producer.flush.assert_called_once()
    mock_producer.close.assert_called_once()


@patch("werkzeug.serving.run_simple")
@patch("pathfinderevents.KafkaProducer")
def test_api_run_server_with_debug(mock_producer, mock_run_simple):
    """Test the run_server function."""
    mock_run_simple.return_value = None
    mock_run_simple.side_effect = None
    api = ApiServer(
        bind_addr="127.0.0.1",
        bind_port=8080,
        realm="test",
        topic="test",
        username="test",
        password="test",  # noqa: S106  # noqa: S106
        debug=True,
    )
    api.set_producer(mock_producer)
    api.run_server()
    mock_run_simple.assert_called_once_with(
        "127.0.0.1",
        8080,
        ANY,
        use_debugger=True,
        use_reloader=True,
    )


@patch("cherrypy.engine.stop")
@patch("cherrypy._cpserver.Server")
@patch("pathfinderevents.KafkaProducer")
def test_api_stop_server(mock_producer, mock_server, mock_stop):
    """Test the stop_server function."""
    api = ApiServer(
        bind_addr="127.0.0.1",
        bind_port=8080,
        realm="test",
        topic="test",
        username="test",
        password="test",  # noqa: S106
        debug=True,
    )
    api.set_producer(mock_producer)
    api._server = mock_server  # noqa: SLF001
    api.stop_server()

    mock_server.stop.assert_called_once_with()
    mock_stop.assert_called_once_with()


@patch("pathfinderevents.sys.exit")
@patch("pathfinderevents.ApiServer")
@patch("pathfinderevents.KafkaProducer")
def test_api_webhook(mock_producer, mock_api, mock_sys_exit):  # noqa: ARG001
    api = ApiServer(
        bind_addr="127.0.0.1",
        bind_port=8080,
        realm="test",
        topic="test",
        username="test",
        password="test",  # noqa: S106
    )
    api.set_producer(mock_producer)
    client = AuthenticatedClient(
        api,
        "test",
        "test",
    )

    resp = client.post(
        _WEBHOOK_ENDPOINT,
        data="event=OnAir&channel=Klangbecken",
        headers={"Content-Type": _CONTENT_TYPE_TEXT},
    )
    assert resp.status_code == 200  # noqa: PLR2004
    assert resp.status == "200 Event Received"
    mock_producer.send.assert_called_once_with(
        "test",
        key="ch.rabe.api.events.pathfinder.v0alpha1.OnAir.Klangbecken",
        value=ANY,
        headers={"content-type": "text/plain".encode("utf-8")},
    )
    value = json.loads(mock_producer.send.call_args.kwargs["value"])
    assert value["data"] == "Klangbecken"
    assert "partitionid" not in value
    assert (
        value["source"] == "https://github.com/radiorabe/pathfinder-cloudevents-service"
    )
    assert value["subject"] == "Klangbecken"
