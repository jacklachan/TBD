"""Operator sign-in for the demo.

**Read this before trusting it with anything.** This is a *convenience gate*,
not authentication. It exists so a judge opening the deployed Space types a name
and a password instead of pasting the server's access token, which keeps that
token off screens, out of screenshots and out of shared chat logs. The
credentials themselves are a shared demo login and default to values checked
into the repository, so anyone who can read the repository can sign in. It
protects the *token*, not the *application*.

What it does buy, which is the whole point:

* The `DESK_ACCESS_TOKEN` — the same secret configured as a Space secret —
  never leaves the server. Signing in mints a **separate** session token, so a
  browser, a screen recording or a bystander never sees the real one.
* A session expires, so a token captured from a demo laptop stops working.
* Failed attempts are rate limited per client, so the endpoint is not a free
  password oracle.

Set ``DESK_ADMIN_USER`` and ``DESK_ADMIN_PASSWORD`` to change the credentials,
and ``DESK_ACCESS_TOKEN`` to the real gate. For anything beyond a judged demo,
replace this with an identity provider; do not grow it.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from dataclasses import dataclass

DEFAULT_USER = "Paan"
DEFAULT_PASSWORD = "Banaras"

# Long enough to outlast a judging session, short enough that a token captured
# from a laptop left open does not keep working the next day.
SESSION_TTL_S = 12 * 3600

# A shared demo login is a single credential many people may try. Cap the
# sessions so a loop cannot grow the table without bound.
MAX_SESSIONS = 64

# Failed attempts per window, per client. Generous for a mistyped password,
# far too slow to search a password space.
MAX_FAILURES = 8
FAILURE_WINDOW_S = 300


def configured_user() -> str:
    return os.environ.get("DESK_ADMIN_USER", DEFAULT_USER).strip() or DEFAULT_USER


def configured_password() -> str:
    return os.environ.get("DESK_ADMIN_PASSWORD", DEFAULT_PASSWORD) or DEFAULT_PASSWORD


@dataclass(frozen=True)
class Session:
    token: str
    user: str
    expires_at: float

    @property
    def expires_in_s(self) -> int:
        return max(0, int(self.expires_at - time.time()))


class TooManyAttempts(RuntimeError):
    """This client has failed too often recently."""


class Operators:
    """Mints and checks session tokens. One instance per application."""

    def __init__(self, ttl_s: float = SESSION_TTL_S) -> None:
        self._ttl = ttl_s
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}
        self._failures: dict[str, list[float]] = {}

    # ----------------------------------------------------------------- login

    def _recent_failures(self, client: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(client, ()) if now - t < FAILURE_WINDOW_S]
        if recent:
            self._failures[client] = recent
        else:
            self._failures.pop(client, None)
        return recent

    def sign_in(self, username: str, password: str, client: str = "") -> Session:
        """Exchange credentials for a session token.

        Both fields are compared in constant time. Comparing the username
        loosely and the password carefully would leak which half was wrong,
        which on a two-field form is most of the answer.
        """
        now = time.time()
        with self._lock:
            if len(self._recent_failures(client, now)) >= MAX_FAILURES:
                raise TooManyAttempts(
                    "Too many failed sign-ins. Wait a few minutes and try again."
                )

            user_ok = secrets.compare_digest(
                (username or "").encode(), configured_user().encode()
            )
            password_ok = secrets.compare_digest(
                (password or "").encode(), configured_password().encode()
            )
            if not (user_ok and password_ok):
                self._failures.setdefault(client, []).append(now)
                raise PermissionError("Those credentials were not recognised.")

            self._failures.pop(client, None)
            self._prune(now)
            if len(self._sessions) >= MAX_SESSIONS:
                oldest = min(self._sessions.values(), key=lambda s: s.expires_at)
                self._sessions.pop(oldest.token, None)

            session = Session(
                token=secrets.token_urlsafe(32),
                user=configured_user(),
                expires_at=now + self._ttl,
            )
            self._sessions[session.token] = session
            return session

    # ---------------------------------------------------------------- verify

    def is_valid(self, token: str) -> bool:
        """True when this token names a session that has not expired.

        Compared against each candidate in constant time: a plain dictionary
        lookup on a secret is a timing signal, and there are at most a few
        dozen sessions, so the cost of doing it properly is nothing.
        """
        if not token:
            return False
        now = time.time()
        with self._lock:
            self._prune(now)
            supplied = token.encode()
            return any(
                secrets.compare_digest(supplied, live.encode())
                for live in self._sessions
            )

    def sign_out(self, token: str) -> bool:
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def _prune(self, now: float) -> None:
        for token, session in list(self._sessions.items()):
            if session.expires_at <= now:
                del self._sessions[token]

    @property
    def active(self) -> int:
        with self._lock:
            self._prune(time.time())
            return len(self._sessions)
