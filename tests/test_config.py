"""The .env reader.

This is the first thing that decides whether a demo has a model at all, and it
fails silently when it is wrong: the key is simply never found, `/health`
reports `model_access: false`, and the workspace says the AI is offline without
saying why. It is twenty lines of hand-rolled parsing and was untested.
"""

from __future__ import annotations

import pytest

from backend.config import load_env


@pytest.fixture
def env_file(tmp_path):
    def write(text: str):
        path = tmp_path / ".env"
        path.write_text(text, encoding="utf-8")
        return path
    return write


def test_an_exported_line_is_read_as_the_bare_key(env_file, monkeypatch):
    """`export KEY=value` is what people paste out of a shell.

    Without handling it the key is stored as "export KEY", nothing ever looks
    that up, and the only symptom is the model reporting itself unavailable.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    loaded = load_env(env_file("export GEMINI_API_KEY=abc123\n"), override=True)
    assert loaded == {"GEMINI_API_KEY": "abc123"}

    from backend.config import gemini_api_key
    assert gemini_api_key() == "abc123"


@pytest.mark.parametrize(
    "line,expected",
    [
        ('KEY="quoted"', "quoted"),
        ("KEY='quoted'", "quoted"),
        ("KEY=bare", "bare"),
        ("KEY =  spaced  ", "spaced"),
        ('KEY="it\'s fine"', "it's fine"),
        # One pair of MATCHING quotes, not every quote character.
        ('KEY=value"', 'value"'),
        ("KEY='mismatched\"", "'mismatched\""),
        ("KEY=", ""),
        # A value may legitimately contain the separator.
        ("KEY=a=b=c", "a=b=c"),
    ],
)
def test_values_are_unwrapped_without_being_corrupted(env_file, monkeypatch, line, expected):
    monkeypatch.delenv("KEY", raising=False)
    assert load_env(env_file(line + "\n"), override=True)["KEY"] == expected


def test_comments_blanks_and_junk_are_skipped(env_file, monkeypatch):
    monkeypatch.delenv("REAL", raising=False)
    loaded = load_env(env_file(
        "# a comment\n"
        "\n"
        "   \n"
        "a line with no separator\n"
        "REAL=yes\n"
    ), override=True)
    assert loaded == {"REAL": "yes"}


def test_an_exported_variable_beats_the_file_unless_told_otherwise(env_file, monkeypatch):
    """An explicitly exported key must win, so a shell can override the file."""
    monkeypatch.setenv("GEMINI_API_KEY", "from-the-shell")
    load_env(env_file("GEMINI_API_KEY=from-the-file\n"))
    from backend.config import gemini_api_key
    assert gemini_api_key() == "from-the-shell"

    load_env(env_file("GEMINI_API_KEY=from-the-file\n"), override=True)
    assert gemini_api_key() == "from-the-file"


def test_a_missing_file_is_not_an_error(tmp_path):
    assert load_env(tmp_path / "nothing-here") == {}


def test_a_key_with_no_name_is_ignored(env_file):
    assert load_env(env_file("=orphaned\n"), override=True) == {}
