"""Create CloudEvents from REST-API Requests."""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import TYPE_CHECKING, Any, NoReturn, Self
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from collections.abc import Iterable
    from wsgiref.types import StartResponse, WSGIEnvironment

import cherrypy  # type: ignore[import-untyped]
from cloudevents.http import CloudEvent
from cloudevents.kafka import to_structured
from configargparse import (  # type: ignore[import-untyped]
    ArgumentParser,
    YAMLConfigFileParser,
)
from kafka import KafkaProducer  # type: ignore[import-untyped]
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule
from werkzeug.wrappers import Request, Response

_RUNTIME_ERROR_MISSING_PRODUCER = "run_server called before set_producer"

logger = logging.getLogger(__name__)


def from_pathfinder_request(request: Request) -> CloudEvent:
    """Convert a basic pathfinder POST request's data into a proper CloudEvent."""
    form = parse_qs(request.get_data(as_text=True))
    return CloudEvent(
        {
            "type": f"ch.rabe.api.events.pathfinder.v0alpha1.{form['event'][0]}",
            "source": "https://github.com/radiorabe/pathfinder-cloudevents-service",
            "subject": form["channel"][0],
            "datacontenttype": "text/plain",
        },
        form["channel"][0],
    )


class ApiServer:
    """The API server."""

    def __init__(  # noqa: PLR0913
        self: Self,
        *,
        bind_addr: str,
        bind_port: int,
        realm: str,
        topic: str,
        username: str,
        password: str,
        debug: bool = False,
    ) -> None:
        """Create ApiServer."""
        self.producer: KafkaProducer
        self.bind_addr: str = bind_addr
        self.bind_port: int = bind_port
        self.realm = realm
        self.topic = topic
        self.username = username
        self.password = password
        self.debug = debug

        self.url_map = Map([Rule("/webhook", endpoint="webhook")])

    def set_producer(self: Self, producer: KafkaProducer) -> None:
        """Set a producer."""
        self.producer = producer

    def run_server(self: Self) -> None:
        """Run the API server."""
        if not self.producer:
            raise RuntimeError(_RUNTIME_ERROR_MISSING_PRODUCER)
        if self.debug:
            from werkzeug.serving import run_simple

            run_simple(
                self.bind_addr,
                self.bind_port,
                self,
                use_debugger=True,
                use_reloader=True,
            )
        else:  # pragma: no cover
            cherrypy.tree.graft(self, "/")
            cherrypy.server.unsubscribe()

            self._server = cherrypy._cpserver.Server()  # noqa: SLF001

            self._server.socket_host = self.bind_addr
            self._server.socket_port = self.bind_port

            self._server.subscribe()

            cherrypy.engine.start()
            cherrypy.engine.block()

    def stop_server(self: Self) -> None:
        """Stop the server."""
        self._server.stop()
        cherrypy.engine.exit()

    def __call__(
        self: Self,
        environ: WSGIEnvironment,
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        """Forward calls to wsgi_app."""
        return self.wsgi_app(environ, start_response)

    def wsgi_app(
        self: Self,
        environ: WSGIEnvironment,
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        """Return a wsgi app."""
        request = Request(environ)
        auth = request.authorization
        if auth and self.check_auth(str(auth.username), str(auth.password)):
            response = self.dispatch_request(request)
        else:
            response = self.auth_required(request)
        return response(environ, start_response)

    def check_auth(self: Self, username: str, password: str) -> bool:
        """Check plaintext auth.

        Pathfinder doesn't support sending any advanced API credentials like JWT or
        similar so we resort to the most insecure way possible to authenticate its
        requests.
        """
        return self.username == username and self.password == password

    def auth_required(self: Self, _: Request) -> Response:
        """Return a 401 unauthorized reponse."""
        return Response(
            "Could not verify your access level for that URL.\n"
            "You have to login with proper credentials",
            status=401,
            headers={"WWW-Authenticate": f'Basic realm="{self.realm}"'},
        )

    def dispatch_request(self: Self, request: Request) -> Response:
        """Dispatch request and return any errors in response."""
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
            return getattr(self, f"on_{endpoint}")(request, **values)
        except HTTPException as e:
            return Response(
                json.dumps(e.description),
                e.code,
                {"Content-Type": "application/json"},
            )

    def on_webhook(self: Self, request: Request) -> Response:
        """Receive a Pathfinder RestApi call and produce a CloudEvent."""

        def on_send_error(ex: Exception) -> None:  # pragma: no cover
            logger.error("Failed to send CloudEvent", exc_info=ex)

        def _key_mapper(ce: CloudEvent) -> Any | None:  # noqa: ANN401
            return ".".join(
                [
                    ce.get("type"),  # type: ignore[list-item]
                    ce.get("subject"),  # type: ignore[list-item]
                ],
            )

        ce = from_pathfinder_request(request)
        kafka_msg = to_structured(
            ce,
            key_mapper=_key_mapper,
        )
        headers: list[tuple[str, bytes]] | None
        if kafka_msg.headers:
            headers = list(kafka_msg.headers.items())
        self.producer.send(
            self.topic,
            key=kafka_msg.key,
            value=kafka_msg.value,
            headers=headers,
        ).add_errback(on_send_error)
        self.producer.flush()
        logger.info(
            "Forwarded event %s with channel %s",
            ce.get("type"),
            ce.get("subject"),
        )
        return Response(
            status="200 Event Received",
        )


def app(  # noqa: PLR0913
    api: ApiServer,
    bootstrap_servers: list[str],
    security_protocol: str,
    tls_cafile: str,
    tls_certfile: str,
    tls_keyfile: str,
) -> None:
    """Set up pathfinder sub, kafka producer & block while processing messages."""
    producer = KafkaProducer(
        bootstrap_servers=bootstrap_servers,
        security_protocol=security_protocol,
        retries=5,
        max_in_flight_requests_per_connection=1,
        key_serializer=lambda k: bytes(k, "utf-8"),
        ssl_cafile=tls_cafile,
        ssl_certfile=tls_certfile,
        ssl_keyfile=tls_keyfile,
    )
    api.set_producer(producer)

    def on_sigint(*_: Any) -> NoReturn:  # noqa: ANN401 # pragma: no cover
        api.stop_server()
        producer.flush()
        producer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)

    api.run_server()  # blocking
    producer.flush()
    producer.close()


def main() -> None:  # pragma: no cover
    """CLI entrypoint parses args, sets up logging, and calls `app()`."""
    parser = ArgumentParser(
        __name__,
        config_file_parser_class=YAMLConfigFileParser,
        default_config_files=[f"{__name__}.yaml"],
    )
    parser.add(
        "--bind-addr",
        default="127.0.0.1",
        env_var="APP_BIND_ADDR",
    )
    parser.add(
        "--bind-port",
        default=8080,
        env_var="APP_BIND_PORT",
    )
    parser.add(
        "--realm",
        default="pathfinder",
        env_var="APP_REALM",
    )
    parser.add(
        "--username",
        default="pathfinder",
        env_var="APP_USERNAME",
    )
    parser.add(
        "--password",
        required=True,
        env_var="APP_PASSWORD",
    )
    parser.add(
        "--kafka-bootstrap-servers",
        required=True,
        env_var="KAFKA_BOOTSTRAP_SERVERS",
    )
    parser.add(
        "--kafka-security-protocol",
        default="PLAINTEXT",
        env_var="KAFKA_SECURITY_PROTOCOL",
    )
    parser.add(
        "--kafka-tls-cafile",
        default=None,
        env_var="KAFKA_TLS_CAFILE",
    )
    parser.add(
        "--kafka-tls-certfile",
        default=None,
        env_var="KAFKA_TLS_CERTFILE",
    )
    parser.add(
        "--kafka-tls-keyfile",
        default=None,
        env_var="KAFKA_TLS_KEYFILE",
    )
    parser.add(
        "--kafka-topic",
        default="dev.cloudevents",
        env_var="KAFKA_TOPIC",
    )
    parser.add(
        "--quiet",
        "-q",
        default=False,
        action="store_true",
        env_var="QUIET",
    )
    parser.add(
        "--debug",
        default=False,
        action="store_true",
        env_var="DEBUG",
    )

    options = parser.parse_args()

    if not options.quiet:
        logging.basicConfig(level=logging.INFO)
    if options.debug:
        logging.basicConfig(level=logging.DEBUG)
    logger.info("Starting %s", __name__)

    app(
        api=ApiServer(
            bind_addr=options.bind_addr,
            bind_port=options.bind_port,
            realm=options.realm,
            username=options.username,
            password=options.password,
            topic=options.kafka_topic,
            debug=options.debug,
        ),
        bootstrap_servers=options.kafka_bootstrap_servers,
        security_protocol=options.kafka_security_protocol,
        tls_cafile=options.kafka_tls_cafile,
        tls_certfile=options.kafka_tls_certfile,
        tls_keyfile=options.kafka_tls_keyfile,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
