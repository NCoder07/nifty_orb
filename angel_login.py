"""
Auto-login to Angel One SmartAPI.

Usage:
    from angel_login import login
    api, session = login()

`api` is an authenticated SmartConnect object ready for data and order calls.
`session` holds the tokens (jwt, refresh, feed) plus login time.

Run directly to test the login:
    python angel_login.py
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import pyotp
import logzero
import SmartApi.smartConnect as _sdk_connect
import SmartApi.smartWebSocketV2 as _sdk_ws
from SmartApi import SmartConnect

log = logging.getLogger("angel_login")

# The SDK logs failed requests together with their full headers, which include
# the API key and the session token. Setting a level on logzero is not enough:
# every SmartConnect() call re-runs logzero.logfile(loglevel=ERROR), which
# lowers the level again. So replace the logger objects the SDK modules hold
# with one that has no handlers and discards everything.
_silenced = logging.getLogger("smartapi.silenced")
_silenced.handlers = [logging.NullHandler()]
_silenced.propagate = False
_silenced.disabled = True
_sdk_connect.logger = _silenced
_sdk_connect.log = _silenced
_sdk_ws.logger = _silenced
logzero.logger.setLevel(logging.CRITICAL + 1)
logzero.logger.propagate = False


def _mask(value):
    """Show only the first two characters of an identifier."""
    value = str(value or "")
    return value[:2] + "*" * max(len(value) - 2, 0)

# Credentials come from environment variables (set once with `setx`):
#   ANGEL_API_KEY      - SmartAPI app key (Trading API type)
#   ANGEL_TOTP_SECRET  - base32 secret shown when enabling TOTP on the SmartAPI portal
#   ANGEL_CLIENT_CODE  - Angel One account ID
#   ANGEL_MPIN         - 4-digit PIN used in the Angel One app
ENV_VARS = ("ANGEL_API_KEY", "ANGEL_TOTP_SECRET", "ANGEL_CLIENT_CODE", "ANGEL_MPIN")

SESSION_FILE = Path(__file__).with_name(".session.json")
MAX_RETRIES = 3


def _creds():
    """Read credentials from the environment. Raises if any are missing."""
    values = {name: os.environ.get(name, "").strip() for name in ENV_VARS}
    missing = [name for name, v in values.items() if not v]
    if missing:
        raise RuntimeError(
            "Missing environment variables: " + ", ".join(missing)
            + ". Set them with `setx NAME value` and open a new terminal."
        )
    return values


def _fresh_login():
    """Log in with client code + MPIN + TOTP. Retries on transient failures."""
    c = _creds()
    api = SmartConnect(api_key=c["ANGEL_API_KEY"])
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        code = pyotp.TOTP(c["ANGEL_TOTP_SECRET"]).now()
        try:
            resp = api.generateSession(c["ANGEL_CLIENT_CODE"], c["ANGEL_MPIN"], code)
        except Exception as exc:  # network / SDK errors
            last_error = str(exc)
            log.warning("login attempt %d raised: %s", attempt, exc)
            time.sleep(2)
            continue

        if resp and resp.get("status"):
            data = resp["data"]
            # The SDK returns the JWT prefixed with "Bearer " but expects the
            # bare token when it is passed back in, so strip the prefix here.
            jwt = data["jwtToken"].removeprefix("Bearer ")
            session = {
                "jwt_token": jwt,
                "refresh_token": data["refreshToken"],
                "feed_token": data["feedToken"],
                "client_code": c["ANGEL_CLIENT_CODE"],
                "login_time": datetime.now().isoformat(timespec="seconds"),
            }
            log.info("logged in as %s", _mask(c["ANGEL_CLIENT_CODE"]))
            return api, session

        last_error = (resp or {}).get("message", "unknown error")
        log.warning("login attempt %d rejected: %s", attempt, last_error)
        # A wrong TOTP usually means clock skew or a code that just rolled over.
        # Wait for the next 30s window before retrying.
        time.sleep(31 - (int(time.time()) % 30))

    raise RuntimeError(f"Angel One login failed after {MAX_RETRIES} attempts: {last_error}")


def _restore(session):
    """Rebuild a SmartConnect from saved tokens and verify they still work."""
    api = SmartConnect(
        api_key=os.environ["ANGEL_API_KEY"],
        access_token=session["jwt_token"],
        refresh_token=session["refresh_token"],
        feed_token=session["feed_token"],
    )
    try:
        prof = api.getProfile(session["refresh_token"])
    except Exception:
        return None
    if prof and prof.get("status"):
        log.info("reused saved session from %s", session["login_time"])
        return api
    return None


def login(force=False):
    """
    Return (api, session). Reuses today's saved session if it is still valid,
    otherwise performs a fresh TOTP login and saves the new tokens.
    """
    creds = _creds()

    if not force and SESSION_FILE.exists():
        try:
            saved = json.loads(SESSION_FILE.read_text())
            same_day = saved.get("login_time", "")[:10] == datetime.now().strftime("%Y-%m-%d")
            same_user = saved.get("client_code") == creds["ANGEL_CLIENT_CODE"]
            if same_day and same_user:
                api = _restore(saved)
                if api is not None:
                    return api, saved
        except (ValueError, KeyError):
            pass

    api, session = _fresh_login()
    SESSION_FILE.write_text(json.dumps(session, indent=2))
    return api, session


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api, session = login()
    profile = api.getProfile(session["refresh_token"])["data"]
    # Never print the client code, name, or tokens: terminal output may be recorded.
    print("Login OK")
    print("  Client   :", _mask(profile.get("clientcode")))
    print("  Exchanges:", ", ".join(profile.get("exchanges", [])))
    print("  Products :", ", ".join(profile.get("products", [])))
    print("  Login at :", session["login_time"])
