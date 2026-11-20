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

## Queue and service

`podscribe add <episode link>` writes the link to a SQLite queue at `paths.data_dir/queue.db` and returns at once. A worker processes jobs one at a time, so intake never waits for an episode and Superwhisper only handles one file at a time.

```sh
uv run podscribe add https://open.spotify.com/episode/...   # queued: <url>
uv run podscribe run             # poll and process forever
uv run podscribe run --once      # drain the queued jobs and exit
uv run podscribe status          # queued / running / done / unmatched / failed
uv run podscribe install-service --dry-run   # print the plist and target path
uv run podscribe install-service             # write ~/Library/LaunchAgents/com.podscribe.worker.plist
```

Adding the same link again is harmless: `add` prints `already done: <note path>`, `already queued` or `already running`.

The worker logs every job start, end and failure to `paths.log_file` (default `~/.podscribe/podscribe.log`). The LaunchAgent starts the worker at login and restarts it after a crash; load it once with the `launchctl bootstrap` command that `install-service` prints. While a job runs and the meetings daemon holds `~/.superwhisper.lock`, `status` appends `waiting for Superwhisper`. podscribe never loads or unloads the service itself.

## Plug your own analyzer

One config-selected component, the analyzer, turns downloaded audio into a transcript and an optional analysis. Pick a backend in `config.yaml`:

```yaml
analyzer:
  backend: command   # superwhisper | command | module
```

- `superwhisper` - default; calls the workflow at `analyzer.superwhisper.wf_path` (SuperwhisperObsidianWF) with its `mode_key`.
- `command` - any executable. podscribe runs it with `{audio}` replaced, never through a shell, and reads stdout as JSON:

  ```json
  {
    "transcript": "full text",
    "analysis": "optional Markdown",
    "segments": [{"start": 0.0, "text": "optional timed line"}]
  }
  ```

  `transcript` is required; `analysis` and `segments` are optional. A non-zero exit, timeout, invalid JSON, a non-object payload or a missing transcript fails the episode with `AnalyzerError`.
- `module` - `package.module:Class`; podscribe instantiates it and calls `analyze(audio: Path, ref: EpisodeRef)`. It may return an `AnalyzerResult` or `(transcript_text, analysis_or_None)`.

The transcript may carry timestamps as word-level `segments` (`{"start", "end", "text"}`); they are grouped into lines of about 20-40 seconds. Without timestamps the whole text becomes one segment at `00:00:00`.

The template's `speech` and `llm` sections are legacy and optional: v1 uses the analyzer instead of local speech plans and cleanup passes.

## Failure notes and notifications

An episode link that produces no note leaves a failure note in `paths.failure_notes_dir`, named `_Failed - <episode title>.md`. It records the episode link, show, reason (`unmatched`, `download`, `analyzer` or `write`), time and the last 20 lines of `paths.log_file`. Unmatched episodes never get an episode note.

When `notifications.macos` is true, every failure also raises a macOS notification. Sending a failed episode link again retries it; a successful run removes that failure note.

