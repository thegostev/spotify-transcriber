import io
import urllib.request


class _Response(io.BytesIO):
    """Minimal urlopen response: a context manager over a byte buffer."""

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class _FakeUrlOpen:
    """Record requests and answer each with a fixed body."""

    def __init__(self, body: bytes) -> None:
        self.body = body
        self.requests: list[tuple[urllib.request.Request, float | None]] = []

    def __call__(self, request: urllib.request.Request, timeout: float | None = None) -> _Response:
        self.requests.append((request, timeout))
        return _Response(self.body)


def test_get_text_fetches_with_the_configured_user_agent(monkeypatch):
    from podscribe.http import HttpClient

    recorder = _FakeUrlOpen(b"hello")
    monkeypatch.setattr("urllib.request.urlopen", recorder)
    client = HttpClient(user_agent="podscribe-test", timeout=5)

    assert client.get_text("https://example.test/page") == "hello"
    request, timeout = recorder.requests[0]
    assert request.full_url == "https://example.test/page"
    assert request.get_header("User-agent") == "podscribe-test"
    assert timeout == 5


def test_get_json_parses_the_response_body(monkeypatch):
    from podscribe.http import HttpClient

    recorder = _FakeUrlOpen(b'{"resultCount": 0, "results": []}')
    monkeypatch.setattr("urllib.request.urlopen", recorder)
    client = HttpClient()

    assert client.get_json("https://example.test/data") == {"resultCount": 0, "results": []}


def test_default_user_agent_identifies_podscribe():
    from podscribe.http import DEFAULT_USER_AGENT

    assert DEFAULT_USER_AGENT.startswith("podscribe/")


def test_download_streams_the_body_into_the_destination(monkeypatch, tmp_path):
    from podscribe.http import HttpClient

    body = b"ID3" + b"\x00" * 5000
    recorder = _FakeUrlOpen(body)
    monkeypatch.setattr("urllib.request.urlopen", recorder)
    client = HttpClient()
    destination = tmp_path / "nested" / "episode.mp3"

    result = client.download("https://example.test/episode.mp3", destination)

    assert result == destination
    assert destination.read_bytes() == body
