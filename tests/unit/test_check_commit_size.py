from check_commit_size import Counts, classify, count_numstat, evaluate, resolve_rename


def test_classifies_paths():
    assert classify("src/podscribe/feed.py") == "production"
    assert classify("tests/unit/test_feed.py") == "test"
    assert classify("scripts/test_helper.py") == "test"
    assert classify("README.md") == "exempt"
    assert classify("uv.lock") == "exempt"
    assert classify("tests/fixtures/episode.html") == "exempt"
    assert classify("config.example.yaml") == "exempt"


def test_resolves_renames():
    assert resolve_rename("src/{a.py => b.py}") == "src/b.py"
    assert resolve_rename("a.py => b.py") == "b.py"
    assert resolve_rename("src/a.py") == "src/a.py"


def test_counts_added_and_deleted_and_ignores_binary():
    numstat = (
        "30\t10\tsrc/podscribe/feed.py\n"
        "50\t0\ttests/unit/test_feed.py\n"
        "-\t-\ttests/fixtures/a.mp3\n"
        "5\t1\tREADME.md\n"
    )
    assert count_numstat(numstat) == Counts(production=40, test=50, exempt=6)


def test_rejects_over_80_production_lines():
    code, message = evaluate(Counts(production=81))
    assert code == 1 and "REJECTED" in message


def test_accepts_80_production_lines():
    assert evaluate(Counts(production=80))[0] == 0


def test_warns_under_20_but_passes():
    code, message = evaluate(Counts(production=5))
    assert code == 0 and "WARNING" in message


def test_test_only_commit_passes_without_warning():
    code, message = evaluate(Counts(test=200))
    assert code == 0 and message.startswith("OK")
