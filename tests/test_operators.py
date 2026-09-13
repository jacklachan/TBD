"""Operator sign-in.

This is a convenience gate, not authentication: the credentials are a shared
demo login. What it must actually deliver is that the server's access token
never reaches a browser, that a session expires, and that the endpoint is not a
free password oracle. Those are the properties tested here.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.operators import (
    DEFAULT_PASSWORD,
    DEFAULT_USER,
    MAX_FAILURES,
    MAX_SESSIONS,
    Operators,
    TooManyAttempts,
)
from backend.store import Store

SERVER_TOKEN = "the-real-space-secret"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DESK_ACCESS_TOKEN", SERVER_TOKEN)
    return TestClient(create_app(store=Store(":memory:")))


def login(client, user=DEFAULT_USER, password=DEFAULT_PASSWORD):
    return client.post("/session/login", json={"username": user, "password": password})


# ---------------------------------------------------------------- the point


def test_signing_in_never_hands_back_the_servers_own_token(client):
    """The whole reason this exists: the real secret stays on the server."""
    body = login(client).json()
    assert body["token"]
    assert body["token"] != SERVER_TOKEN
    assert SERVER_TOKEN not in str(body)


def test_a_session_token_opens_the_api(client):
    token = login(client).json()["token"]
    assert client.post("/cases", json={"scenario_id": "primary"},
                       headers={"Authorization": f"Bearer {token}"}).status_code == 201


def test_the_api_is_still_shut_without_one(client):
    assert client.post("/cases", json={"scenario_id": "primary"}).status_code == 401
    assert client.post("/cases", json={"scenario_id": "primary"},
                       headers={"Authorization": "Bearer not-a-session"}).status_code == 401


def test_the_configured_token_still_works_directly(client):
    """Sign-in is added alongside the token, not in place of it."""
    assert client.post("/cases", json={"scenario_id": "primary"},
                       headers={"Authorization": f"Bearer {SERVER_TOKEN}"}).status_code == 201


# ------------------------------------------------------------- credentials


@pytest.mark.parametrize("user,password", [
    ("Paan", "wrong"),
    ("wrong", "Banaras"),
    ("paan", "Banaras"),      # case matters
    ("Paan ", "Banaras"),     # and so does whitespace
])
def test_bad_credentials_are_refused(client, user, password):
    assert login(client, user, password).status_code == 401


def test_an_empty_field_is_rejected_as_malformed_not_as_a_guess(client):
    """422, not 401: a blank field never reaches the credential check, so it
    does not spend an attempt from the rate limiter either."""
    assert login(client, "", "").status_code == 422


def test_the_refusal_does_not_say_which_half_was_wrong(client):
    """On a two-field form, naming the wrong field hands back half the answer."""
    wrong_user = login(client, "nobody", DEFAULT_PASSWORD).json()["detail"]["message"]
    wrong_pass = login(client, DEFAULT_USER, "nonsense").json()["detail"]["message"]
    assert wrong_user == wrong_pass


def test_credentials_can_be_changed_by_configuration(monkeypatch):
    monkeypatch.setenv("DESK_ACCESS_TOKEN", SERVER_TOKEN)
    monkeypatch.setenv("DESK_ADMIN_USER", "flight")
    monkeypatch.setenv("DESK_ADMIN_PASSWORD", "correct horse")
    c = TestClient(create_app(store=Store(":memory:")))
    assert login(c, "flight", "correct horse").status_code == 200
    assert login(c, DEFAULT_USER, DEFAULT_PASSWORD).status_code == 401


# ------------------------------------------------------------------ limits


def test_repeated_failures_are_rate_limited(client):
    for _ in range(MAX_FAILURES):
        assert login(client, DEFAULT_USER, "nope").status_code == 401
    refused = login(client, DEFAULT_USER, "nope")
    assert refused.status_code == 429
    # And the correct password is refused too while the window is open, or the
    # limit would be trivially skipped by guessing right on the next attempt.
    assert login(client).status_code == 429


def test_a_successful_sign_in_clears_the_failure_count():
    operators = Operators()
    for _ in range(MAX_FAILURES - 1):
        with pytest.raises(PermissionError):
            operators.sign_in(DEFAULT_USER, "nope", client="a")
    operators.sign_in(DEFAULT_USER, DEFAULT_PASSWORD, client="a")
    for _ in range(MAX_FAILURES - 1):
        with pytest.raises(PermissionError):
            operators.sign_in(DEFAULT_USER, "nope", client="a")


def test_one_client_cannot_lock_out_another():
    operators = Operators()
    for _ in range(MAX_FAILURES + 2):
        with pytest.raises((PermissionError, TooManyAttempts)):
            operators.sign_in(DEFAULT_USER, "nope", client="noisy")
    assert operators.sign_in(DEFAULT_USER, DEFAULT_PASSWORD, client="quiet").token


def test_a_session_expires():
    operators = Operators(ttl_s=0.05)
    token = operators.sign_in(DEFAULT_USER, DEFAULT_PASSWORD).token
    assert operators.is_valid(token)
    time.sleep(0.08)
    assert not operators.is_valid(token)
    assert operators.active == 0


def test_sessions_do_not_grow_without_bound():
    operators = Operators()
    for _ in range(MAX_SESSIONS + 15):
        operators.sign_in(DEFAULT_USER, DEFAULT_PASSWORD)
    assert operators.active <= MAX_SESSIONS


def test_signing_out_ends_the_session(client):
    token = login(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/session/logout", headers=headers).json()["ended"] is True
    assert client.post("/cases", json={"scenario_id": "primary"}, headers=headers).status_code == 401


def test_each_sign_in_mints_a_distinct_token(client):
    assert login(client).json()["token"] != login(client).json()["token"]


# -------------------------------------------------------------- no token set


def test_a_server_with_no_token_says_it_needs_no_sign_in(monkeypatch):
    monkeypatch.delenv("DESK_ACCESS_TOKEN", raising=False)
    c = TestClient(create_app(store=Store(":memory:")))
    assert c.get("/health").json()["sign_in_enabled"] is False
    assert login(c).status_code == 409


def test_health_stays_public_so_the_page_can_ask_whether_to_show_the_form(client):
    body = client.get("/health").json()
    assert body["sign_in_enabled"] is True
    assert body["access_token_required"] is True
