"""That the index in this folder's `README.md` names every test, and nothing
else.

It is the same rule as the index of A Blurred Line's tests, and for the same
reason: a hand-written index goes stale without warning. It does not check
whether what it says about each one is true; it checks that they are all
there and that they exist.
"""

import glob
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, "README.md")

# A bare file name: tests here do not go in subfolders.
NAMED = re.compile(r"`(test_\w+\.py)`")


def _on_disk():
    return {os.path.basename(r)
            for r in glob.glob(os.path.join(HERE, "test_*.py"))}


def _in_the_index():
    with open(README, encoding="utf-8") as f:
        text = f.read()
    sections = text.split("## Which test covers what", 1)
    assert len(sections) == 2, "README.md no longer has \"Which test covers what\""
    return set(NAMED.findall(sections[1]))


def test_every_test_is_in_the_index():
    missing = sorted(_on_disk() - _in_the_index())
    assert not missing, (
        "the index in tests/README.md does not name: %s"
        % ", ".join(missing))


def test_the_index_names_no_missing_tests():
    extra = sorted(_in_the_index() - _on_disk())
    assert not extra, (
        "the index in tests/README.md names tests that do not exist: "
        "%s. Were they renamed or deleted?" % ", ".join(extra))
