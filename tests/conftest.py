from base64 import b64encode
from unittest.mock import AsyncMock

import pytest

from pathfinderevents import app as quart_app

AUTH_HEADERS = {"Authorization": f"Basic {b64encode(b'test:test').decode()}"}


@pytest.fixture
def mock_producer():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _configure_app(mock_producer):
    quart_app.config.update(
        {
            "TESTING": True,
            "REALM": "test",
            "USERNAME": "test",
            "PASSWORD": "test",
            "TOPIC": "test",
            "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
            "KAFKA_SECURITY_PROTOCOL": "PLAINTEXT",
            "KAFKA_TLS_CAFILE": None,
            "KAFKA_TLS_CERTFILE": None,
            "KAFKA_TLS_KEYFILE": None,
            "PRODUCER": mock_producer,
        },
    )
