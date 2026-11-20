# podscribe

Spotify episode link → show's public feed → audio → transcript → episode note in an Obsidian vault. Runs as a LaunchAgent on a Mac mini (8 GB RAM - Metal can use about 5 GB of it). The repo is public.

## Domain

Glossary: `../CONTEXT.md`. Use its terms in code, tests, commits and tickets. Decisions: `../docs/adr/` - read before changing the audio source, a speech engine or the LLM provider. Both live outside the repo (private docs root); a public clone has neither.

## Flow - AI Hero (overrides the workspace Spec Kit rule)

Work comes from Linear tickets in project P-LAG-102, team Lag. Product spec: the PRD document on that project. One ticket = one vertical slice; the first build ticket is the tracer bullet.

For each behaviour in a ticket:

1. `test:` commit - a test that states the behaviour before it exists, written from the ticket's acceptance criteria. Mark it `@pytest.mark.xfail(strict=True, reason="LAG-###")`. It is red.
2. `feat:` / `fix:` commit - production code turns it green; remove the xfail marker in this commit.
3. `refactor:` commits as needed, staying green.

Tests are the validator of what should be built, not a confirmation of what was built.

A ticket is done when every acceptance criterion is checked and Alex has reviewed it. Alex moves Linear states.

## Commits - enforced by `.githooks/`

- 20-80 production lines per commit (added + deleted). Tests, docs, lockfiles, fixtures and config templates are not counted. Over 80: the hook rejects - split the slice.
- Subject: `<type>(<scope>): <summary> LAG-###`. Types: feat, fix, test, refactor, chore, docs, perf, build, ci.
- `pytest -m "not slow"` green before every commit (strict xfail counts as green).

## Code

- Python 3.13 with uv: `uv sync`, `uv run pytest`, `uv run ruff check`.
- Layout: `src/podscribe/`; tests in `tests/unit|integration|contract/`; recorded HTTP responses in `tests/fixtures/`.
- Type hints everywhere, Google docstrings on public functions, `pathlib`, `argparse`, UPPER_SNAKE constants at module top, timestamped log lines.
- Every command that writes files supports `--dry-run`.
- External HTTP (Spotify page, iTunes Search, feeds, Ollama) goes through one client module, so tests swap in fixtures.
- One speech model in memory at a time. Tests that load a model or real audio are marked `slow`.
- File names written to a vault are Obsidian-safe: strip `: [ ] # ^ | \ * " ? < >`.

## Config and secrets

- Every path, host, model and prompt lives in `config.yaml` (gitignored). Add each new key to `config.example.yaml` in the same commit.
- Secrets live in the macOS Keychain. Config holds `keychain_service` + `keychain_account`; code reads the value with `security find-generic-password -s <service> -a <account> -w`. Values stay out of code, logs, fixtures and commits.

## Reuse

Copy, don't import, from `../../RecordingAnalyser/`: `pipeline.py` (mlx-whisper wrapper, `classify_ollama_error`, retry backoff), `config.py` (loader), launchd pattern (its `docs/adr/0002`). Read its post-mortem `26-04-24 - Parakeet OOM System Freeze` before writing speech code.

## Tools

Helpers that are not product code (one-off scripts, pi skills, prompt templates) go to `~/Documents/Obsidian/tools/`. Product code never imports from there.

## Session end

Update `../session.md`: what was done, current state, open questions, next ticket.
