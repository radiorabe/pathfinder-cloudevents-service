"""Create CloudEvents from REST-API Requests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

if TYPE_CHECKING:
    from cloudevents.core.base import BaseCloudEvent

import click
import typed_settings as ts
from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]
from cloudevents.core.bindings.kafka import to_structured_event
from cloudevents.core.v1.event import CloudEvent
from quart import Quart, Response, request

logger = logging.getLogger(__name__)

app = Quart(__name__)


@ts.settings
class AppSettings:
    """Application server settings."""

    password: str = ts.secret(help="Basic auth password")
    bind_addr: str = ts.option(default="127.0.0.1", help="Bind address")
    bind_port: int = ts.option(default=8080, help="Bind port")
    realm: str = ts.option(default="pathfinder", help="Basic auth realm")
    username: str = ts.option(default="pathfinder", help="Basic auth username")
    quiet: bool = ts.option(default=False, help="Suppress log output")
    debug: bool = ts.option(default=False, help="Enable debug mode")


@ts.settings
class KafkaSettings:
    """Kafka producer settings."""

    bootstrap_servers: str = ts.option(help="Bootstrap servers (comma-separated)")
    topic: str = ts.option(default="dev.cloudevents", help="Target topic")
    security_protocol: str = ts.option(default="PLAINTEXT", help="Security protocol")
    tls_cafile: str | None = ts.option(default=None, help="TLS CA certificate file")
    tls_certfile: str | None = ts.option(
        default=None,
        help="TLS client certificate file",
    )
    tls_keyfile: str | None = ts.option(default=None, help="TLS client key file")


@ts.settings
class Settings:
    """Top-level settings composed from sub-settings."""

    app: AppSettings = ts.option(factory=AppSettings)
    kafka: KafkaSettings = ts.option(factory=KafkaSettings)


_LOADERS = [ts.EnvLoader(prefix="", nested_delimiter="_")]


def _serialize_key(k: str | bytes | None) -> bytes | None:
    """Serialize a Kafka message key to bytes."""
    if isinstance(k, str):
        return k.encode("utf-8")
    return k


def from_pathfinder_request_data(data: str) -> CloudEvent:
    """Convert pathfinder POST request data into a CloudEvent."""
    form = parse_qs(data)
    return CloudEvent(
        attributes={
            "type": f"ch.rabe.api.events.pathfinder.v0alpha1.{form['event'][0]}",
            "source": "https://github.com/radiorabe/pathfinder-cloudevents-service",
            "subject": form["channel"][0],
            "datacontenttype": "text/plain",
        },
        data=form["channel"][0],
    )


@app.before_serving
async def start_producer() -> None:
    """Start the Kafka producer before serving requests."""
    if "PRODUCER" in app.config:
        return
    producer = AIOKafkaProducer(
        bootstrap_servers=app.config["KAFKA_BOOTSTRAP_SERVERS"],
        security_protocol=app.config["KAFKA_SECURITY_PROTOCOL"],
        ssl_cafile=app.config.get("KAFKA_TLS_CAFILE"),
        ssl_certfile=app.config.get("KAFKA_TLS_CERTFILE"),
        ssl_keyfile=app.config.get("KAFKA_TLS_KEYFILE"),
        retries=5,
        max_in_flight_requests_per_connection=1,
        key_serializer=_serialize_key,
    )
    await producer.start()
    app.config["PRODUCER"] = producer


@app.after_serving
async def stop_producer() -> None:
    """Stop the Kafka producer after serving."""
    producer: AIOKafkaProducer | None = app.config.get("PRODUCER")
    if producer is not None:
        await producer.flush()
        await producer.stop()


@app.route("/webhook", methods=["POST"])
async def webhook() -> Response:
    """Receive a Pathfinder RestApi call and produce a CloudEvent."""
    auth = request.authorization
    if (
        not auth
        or auth.username != app.config["USERNAME"]
        or auth.password != app.config["PASSWORD"]
    ):
        return Response(
            "Could not verify your access level for that URL.\n"
            "You have to login with proper credentials",
            status=401,
            headers={"WWW-Authenticate": f'Basic realm="{app.config["REALM"]}"'},
        )

    raw = await request.get_data()
    data = raw.decode() if isinstance(raw, bytes) else raw
    ce = from_pathfinder_request_data(data)

    def _key_mapper(cloud_event: BaseCloudEvent) -> str | bytes | None:
        return f"{cloud_event.get_type()}.{cloud_event.get_subject()}"

    kafka_msg = to_structured_event(ce, key_mapper=_key_mapper)
    headers: list[tuple[str, bytes]] | None = None
    if kafka_msg.headers:
        headers = list(kafka_msg.headers.items())

    producer: AIOKafkaProducer = app.config["PRODUCER"]
    await producer.send(
        app.config["TOPIC"],
        key=kafka_msg.key,
        value=kafka_msg.value,
        headers=headers,
    )
    await producer.flush()
    logger.info(
        "Forwarded event %s with channel %s",
        ce.get_type(),
        ce.get_subject(),
    )
    return Response(status=200)


@click.command()
@ts.click_options(Settings, _LOADERS, show_envvars_in_help=True)
def main(settings: Settings) -> None:  # pragma: no cover
    """Subscribe to Axia Pathfinder Events and send them to Kafka as CloudEvents."""
    if not settings.app.quiet:
        logging.basicConfig(level=logging.INFO)
    if settings.app.debug:
        logging.basicConfig(level=logging.DEBUG)
    logger.info("Starting %s", __name__)

    app.config.update(
        {
            "REALM": settings.app.realm,
            "USERNAME": settings.app.username,
            "PASSWORD": settings.app.password,
            "TOPIC": settings.kafka.topic,
            "KAFKA_BOOTSTRAP_SERVERS": settings.kafka.bootstrap_servers,
            "KAFKA_SECURITY_PROTOCOL": settings.kafka.security_protocol,
            "KAFKA_TLS_CAFILE": settings.kafka.tls_cafile,
            "KAFKA_TLS_CERTFILE": settings.kafka.tls_certfile,
            "KAFKA_TLS_KEYFILE": settings.kafka.tls_keyfile,
        },
    )

    app.run(
        host=settings.app.bind_addr,
        port=settings.app.bind_port,
        debug=settings.app.debug,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
