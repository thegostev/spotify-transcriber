# podscribe

Send a Spotify podcast episode link; get a transcribed, cleaned and summarised Markdown note in your Obsidian vault.

Audio comes from the show's public RSS feed, never from Spotify. Spotify-exclusive episodes are reported as unmatched.

Status: early development.

## Setup

```sh
uv sync
cp config.example.yaml config.yaml   # edit paths, models, Keychain references
uv run pytest
```
