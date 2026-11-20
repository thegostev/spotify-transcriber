from check_commit_msg import check_message


def test_accepts_conventional_subject_with_issue():
    assert check_message("feat(feed): match feed item by date LAG-1046\n")[0] == 0


def test_accepts_issue_in_footer():
    assert check_message("test: describe feed matching\n\nRefs: LAG-1046\n")[0] == 0


def test_rejects_missing_type():
    assert check_message("match feed item LAG-1046")[0] == 1


def test_rejects_missing_issue():
    assert check_message("fix: handle empty feed")[0] == 1


def test_ignores_comment_lines():
    assert check_message("# LAG-1\nfix: handle empty feed\n")[0] == 1


def test_lets_merge_commits_through():
    assert check_message("Merge branch 'main'")[0] == 0
