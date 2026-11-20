from datetime import date
from pathlib import Path

AUDIO_URL = "https://traffic.megaphone.fm/SCIM7125421200.mp3?updated=1747806938"


class _FakeClient:
    """Record download calls and write a fixed body."""

    def __init__(self, body: bytes = b"ID3audio") -> None:
        self.body = body
        self.calls: list[tuple[str, Path]] = []

    def download(self, url: str, destination: Path) -> Path:
        self.calls.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.body)
        return destination


def _item(audio_url: str):
    from podscribe.models import FeedItem

    return FeedItem(title="Episode", published_at=date(2022, 11, 28), audio_url=audio_url)


def test_download_audio_writes_the_enclosure_into_the_directory(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient()
    directory = tmp_path / "working"

    result = download_audio(_item(AUDIO_URL), directory, client)

    assert result == directory / "SCIM7125421200.mp3"
    assert result.read_bytes() == b"ID3audio"
    assert client.calls == [(AUDIO_URL, result)]


def test_download_audio_falls_back_to_a_default_name_without_a_path(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient()

    result = download_audio(_item("https://cdn.example"), tmp_path, client)

    assert result.name == "episode.mp3"


def test_download_audio_keeps_an_existing_file_unless_overwrite_is_set(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient(b"new")
    existing = tmp_path / "SCIM7125421200.mp3"
    existing.write_bytes(b"old")

    assert download_audio(_item(AUDIO_URL), tmp_path, client) == existing
    assert existing.read_bytes() == b"old"
    assert client.calls == []


def test_download_audio_overwrites_when_asked(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient(b"new")
    existing = tmp_path / "SCIM7125421200.mp3"
    existing.write_bytes(b"old")

    assert download_audio(_item(AUDIO_URL), tmp_path, client, overwrite=True) == existing
    assert existing.read_bytes() == b"new"
    assert len(client.calls) == 1
