import asyncio
from http.cookies import SimpleCookie
import json
import tempfile
import unittest

try:
    from starlette.applications import Starlette

    from zuru_upload_routes import API_PREFIX, create_upload_routes
    from zuru_upload_staging import UploadStagingRegistry

    ROUTE_TESTS_AVAILABLE = True
except ModuleNotFoundError:
    ROUTE_TESTS_AVAILABLE = False


class AsgiClient:
    """Dependency-free HTTP harness for the experiment's Starlette routes."""

    def __init__(self, app):
        self.app = app
        self.cookies = {}

    def request(self, method, path, *, headers=None, json_body=None, content=b""):
        request_headers = {"host": "preview.example", **(headers or {})}
        if self.cookies:
            request_headers["cookie"] = "; ".join(
                f"{name}={value}" for name, value in self.cookies.items()
            )
        if json_body is not None:
            content = json.dumps(json_body).encode("utf-8")
            request_headers.setdefault("content-type", "application/json")
        request_headers.setdefault("content-length", str(len(content)))
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in request_headers.items()
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("preview.example", 443),
        }
        messages = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": content, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        asyncio.run(self.app(scope, receive, send))
        start = next(
            message for message in messages if message["type"] == "http.response.start"
        )
        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.response.body"
        )
        response_headers = [
            (name.decode("latin-1"), value.decode("latin-1"))
            for name, value in start["headers"]
        ]
        for name, value in response_headers:
            if name.lower() == "set-cookie":
                parsed = SimpleCookie()
                parsed.load(value)
                for cookie_name, morsel in parsed.items():
                    self.cookies[cookie_name] = morsel.value
        return start["status"], json.loads(body)


@unittest.skipUnless(
    ROUTE_TESTS_AVAILABLE, "Streamlit/Starlette test dependencies unavailable"
)
class TestUploadRoutes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry = UploadStagingRegistry(root=self.temp_dir.name, ttl_seconds=60)
        self.app = Starlette(routes=create_upload_routes(self.registry))
        self.client = AsgiClient(self.app)
        status, bootstrap = self.client.request("GET", f"{API_PREFIX}/bootstrap")
        self.assertEqual(status, 200)
        self.xsrf = bootstrap["xsrf_token"]
        self.headers = {
            "origin": "https://preview.example",
            "x-zuru-xsrf": self.xsrf,
        }

    def tearDown(self):
        self.registry.close()
        self.temp_dir.cleanup()

    def test_complete_owner_bound_explicit_claim_flow(self):
        status, intent = self.client.request(
            "POST",
            f"{API_PREFIX}/intents",
            headers=self.headers,
            json_body={"filename": "Sana fasadi.dwg", "size": 6},
        )
        self.assertEqual(status, 201)
        upload_id = intent["upload_id"]

        status, uploaded_response = self.client.request(
            "PUT",
            f"{API_PREFIX}/intents/{upload_id}/bytes",
            headers={**self.headers, "content-type": "application/octet-stream"},
            content=b"DWG123",
        )
        self.assertEqual(status, 200)
        self.assertTrue(uploaded_response["ready"])

        status, claim_response = self.client.request(
            "POST", f"{API_PREFIX}/intents/{upload_id}/claim", headers=self.headers
        )
        self.assertEqual(status, 200)
        uploaded = self.registry.consume_claim(claim_response["claim_token"])
        self.assertEqual(uploaded.name, "Sana fasadi.dwg")
        self.assertEqual(uploaded.getvalue(), b"DWG123")

    def test_mutations_reject_missing_xsrf_and_cross_origin(self):
        for headers in (
            {"origin": "https://preview.example"},
            {"origin": "https://attacker.example", "x-zuru-xsrf": self.xsrf},
        ):
            with self.subTest(headers=headers):
                status, _ = self.client.request(
                    "POST",
                    f"{API_PREFIX}/intents",
                    headers=headers,
                    json_body={"filename": "drawing.dxf", "size": 3},
                )
                self.assertEqual(status, 400)

    def test_other_browser_cannot_observe_or_claim_upload(self):
        _, intent = self.client.request(
            "POST",
            f"{API_PREFIX}/intents",
            headers=self.headers,
            json_body={"filename": "private.dxf", "size": 3},
        )
        other = AsgiClient(self.app)
        _, bootstrap = other.request("GET", f"{API_PREFIX}/bootstrap")
        other_headers = {
            "origin": "https://preview.example",
            "x-zuru-xsrf": bootstrap["xsrf_token"],
        }
        status, pending = other.request("GET", f"{API_PREFIX}/pending")
        self.assertEqual(status, 200)
        self.assertEqual(pending["uploads"], [])
        status, _ = other.request(
            "POST",
            f"{API_PREFIX}/intents/{intent['upload_id']}/claim",
            headers=other_headers,
        )
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
