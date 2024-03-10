from base64 import b64encode

from werkzeug.test import Client
from werkzeug.wrappers import Response


class AuthenticatedClient(Client):
    """An authenticated client for testing."""

    def __init__(self, app, user, password):
        super().__init__(app, Response)
        self.user = user
        self.password = password

    def post(self, *args, **kwargs):
        if "headers" not in kwargs:  # pragma: no cover
            kwargs["headers"] = {}
        if "Authorization" not in kwargs["headers"]:
            pwd = b64encode(f"{self.user}:{self.password}".encode()).decode("utf-8")
            kwargs["headers"]["Authorization"] = f"Basic {pwd}"
        return super().post(*args, **kwargs)
