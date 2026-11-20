import hashlib
from datetime import date
from pathlib import Path

AUDIO_URL = "https://traffic.megaphone.fm/SCIM7125421200.mp3?updated=1747806938"


def _tag(url: str) -> str:
    """Return the short stable URL tag expected in a cache name."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]


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

    assert result == directory / f"SCIM7125421200-{_tag(AUDIO_URL)}.mp3"
    assert result.read_bytes() == b"ID3audio"
    assert client.calls == [(AUDIO_URL, result)]


def test_download_audio_falls_back_to_a_default_name_without_a_path(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient()

    result = download_audio(_item("https://cdn.example"), tmp_path, client)

    assert result.name == f"episode-{_tag('https://cdn.example')}.mp3"


def test_download_audio_reuses_the_file_for_the_same_url(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient(b"first")
    first = download_audio(_item(AUDIO_URL), tmp_path, client)
    first.write_bytes(b"cached")

    assert download_audio(_item(AUDIO_URL), tmp_path, client) == first
    assert first.read_bytes() == b"cached"
    assert len(client.calls) == 1


def test_download_audio_keeps_same_basename_urls_apart(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient()
    first_url = "https://a.example/SCIM7125421200.mp3"
    second_url = "https://b.example/SCIM7125421200.mp3"

    first = download_audio(_item(first_url), tmp_path, client)
    second = download_audio(_item(second_url), tmp_path, client)

    assert first != second
    assert client.calls == [(first_url, first), (second_url, second)]
    assert first.read_bytes() == second.read_bytes() == b"ID3audio"


def test_download_audio_names_a_basename_less_url_deterministically(tmp_path):
    from podscribe.download import download_audio

    url = "https://cdn.example"
    expected = f"episode-{_tag(url)}.mp3"

    first = download_audio(_item(url), tmp_path, _FakeClient())
    second = download_audio(_item(url), tmp_path / "other", _FakeClient())

    assert first.name == expected
    assert second.name == expected


def test_download_audio_keeps_an_existing_file_unless_overwrite_is_set(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient(b"new")
    existing = tmp_path / f"SCIM7125421200-{_tag(AUDIO_URL)}.mp3"
    existing.write_bytes(b"old")

    assert download_audio(_item(AUDIO_URL), tmp_path, client) == existing
    assert existing.read_bytes() == b"old"
    assert client.calls == []


def test_download_audio_overwrites_when_asked(tmp_path):
    from podscribe.download import download_audio

    client = _FakeClient(b"new")
    existing = tmp_path / f"SCIM7125421200-{_tag(AUDIO_URL)}.mp3"
    existing.write_bytes(b"old")

    assert download_audio(_item(AUDIO_URL), tmp_path, client, overwrite=True) == existing
    assert existing.read_bytes() == b"new"
    assert len(client.calls) == 1
