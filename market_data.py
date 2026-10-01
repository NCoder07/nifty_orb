"""Candles from the historical API, live LTP from the WebSocket, and a tick-built candle fallback."""

import datetime as dt
import logging
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from SmartApi.smartWebSocketV2 import SmartWebSocketV2

import config
from instruments import Instrument

log = logging.getLogger("market_data")

INTERVAL_NAMES = {1: "ONE_MINUTE", 3: "THREE_MINUTE", 5: "FIVE_MINUTE", 10: "TEN_MINUTE",
                  15: "FIFTEEN_MINUTE", 30: "THIRTY_MINUTE", 60: "ONE_HOUR"}


@dataclass
class Candle:
    start: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def close_time(self) -> dt.datetime:
        return self.start + dt.timedelta(minutes=config.CANDLE_MINUTES)

    @property
    def label(self) -> str:
        return self.start.strftime("%H:%M")

    def to_list(self):
        return [self.start.isoformat(), self.open, self.high, self.low, self.close, self.volume]

    @classmethod
    def from_list(cls, row):
        return cls(dt.datetime.fromisoformat(row[0]), float(row[1]), float(row[2]),
                   float(row[3]), float(row[4]), float(row[5]) if len(row) > 5 else 0.0)


def fetch_candles(api, inst: Instrument, day: dt.date, retries: int = 3) -> Optional[List[Candle]]:
    """
    A day's candles from the historical API.
    Returns [] when the exchange has no data (holiday / before open) and None on API failure.
    """
    params = {
        "exchange": inst.exchange,
        "symboltoken": inst.token,
        "interval": INTERVAL_NAMES[config.CANDLE_MINUTES],
        "fromdate": f"{day:%Y-%m-%d} 09:00",
        "todate": f"{day:%Y-%m-%d} 15:35",
    }
    # Angel's historical endpoint often throttles the first request after a quiet
    # spell ("exceeding access rate") and accepts a retry a little later. Hitting
    # it again too quickly escalates to "Too many requests", so back off between
    # tries and only report the final failure as a warning.
    for attempt in range(1, retries + 1):
        level = logging.WARNING if attempt == retries else logging.DEBUG
        try:
            resp = api.getCandleData(params)
        except Exception as exc:
            msg = str(exc)
            log.log(level, "candle fetch attempt %d failed: %s", attempt, msg[:100])
        else:
            if resp and resp.get("status"):
                return [Candle.from_list(r) for r in (resp.get("data") or [])]
            msg = str((resp or {}).get("message", "no response"))
            log.log(level, "candle fetch attempt %d rejected: %s", attempt, msg)
        throttled = "rate" in msg.lower() or "many requests" in msg.lower()
        time.sleep((4 if throttled else 2) * attempt)
    return None


class CandleBuilder:
    """Builds candles from ticks. Used only when the historical API fails for a candle."""

    def __init__(self):
        self._lock = threading.Lock()
        self._done: Dict[dt.datetime, Candle] = {}
        self._cur: Optional[Candle] = None

    @staticmethod
    def _bucket(ts: dt.datetime) -> dt.datetime:
        m = ts.minute - ts.minute % config.CANDLE_MINUTES
        return ts.replace(minute=m, second=0, microsecond=0)

    def on_tick(self, price: float, ts: dt.datetime):
        b = self._bucket(ts)
        with self._lock:
            if self._cur is None or self._cur.start != b:
                if self._cur is not None:
                    self._done[self._cur.start] = self._cur
                self._cur = Candle(b, price, price, price, price)
            else:
                c = self._cur
                c.high = max(c.high, price)
                c.low = min(c.low, price)
                c.close = price

    def get(self, start: dt.datetime) -> Optional[Candle]:
        with self._lock:
            return self._done.get(start)


class TickFeed:
    """Thread-safe last-traded-price store fed by the SmartAPI WebSocket V2."""

    def __init__(self, api_key: str, client_code: str, jwt_token: str, feed_token: str,
                 instruments: List[Instrument], builder_token: Optional[str] = None,
                 builder: Optional[CandleBuilder] = None, tz=None):
        self._api_key = api_key
        self._client_code = client_code
        # The socket wants the header value exactly as the login returned it, with "Bearer ".
        self._jwt = jwt_token if jwt_token.startswith("Bearer ") else "Bearer " + jwt_token
        self._feed_token = feed_token
        self._instruments = instruments
        self._builder_token = builder_token
        self._builder = builder
        self._tz = tz
        self._ltp: Dict[str, float] = {}
        self._lock = threading.Lock()
        self._ws: Optional[SmartWebSocketV2] = None
        self._thread: Optional[threading.Thread] = None
        self.connected = False
        self.started_at: float = 0.0
        self.last_tick_at: float = 0.0

    # -- callbacks; the SDK passes the websocket app as the first argument --
    def _on_open(self, wsapp):
        groups: Dict[int, List[str]] = {}
        for inst in self._instruments:
            groups.setdefault(inst.ws_exchange, []).append(inst.token)
        token_list = [{"exchangeType": ex, "tokens": toks} for ex, toks in groups.items()]
        self._ws.subscribe("orb", SmartWebSocketV2.LTP_MODE, token_list)
        self.connected = True
        log.info("tick feed connected, subscribed %d instrument(s)", len(self._instruments))

    def _on_data(self, wsapp, msg):
        price = msg.get("last_traded_price")
        token = str(msg.get("token", ""))
        if price is None or not token:
            return
        price = price / 100.0
        with self._lock:
            self._ltp[token] = price
        self.last_tick_at = time.time()
        if self._builder is not None and token == self._builder_token:
            self._builder.on_tick(price, dt.datetime.now(self._tz))

    def _on_error(self, *args):
        log.warning("tick feed error: %s", " ".join(str(a) for a in args[-2:]))

    def _on_close(self, *args):
        self.connected = False
        log.warning("tick feed closed")

    # -- public API --
    def start(self):
        ws = SmartWebSocketV2(self._jwt, self._api_key, self._client_code, self._feed_token,
                              max_retry_attempt=5, retry_delay=5)
        ws.on_open = self._on_open
        ws.on_data = self._on_data
        ws.on_error = self._on_error
        ws.on_close = self._on_close
        # The SDK's internal close handler accepts one argument, but websocket-client
        # passes three. The resulting exception is routed to the SDK's error handler,
        # which then reconnects even after an intentional stop. Replace it.
        ws._on_close = lambda wsapp, *args: self._on_close(wsapp)
        self._ws = ws
        self.started_at = time.time()
        self._thread = threading.Thread(target=ws.connect, name="tick-feed", daemon=True)
        self._thread.start()

    def stop(self):
        self.connected = False
        try:
            if self._ws is not None:
                self._ws.MAX_RETRY_ATTEMPT = 0      # no auto-reconnect after a deliberate stop
                self._ws.close_connection()
        except Exception:
            pass

    def restart(self):
        log.warning("restarting tick feed")
        self.stop()
        time.sleep(2)
        self.start()

    def ltp(self, token: str) -> Optional[float]:
        with self._lock:
            return self._ltp.get(token)

    def stale(self, seconds: float) -> bool:
        last = self.last_tick_at or self.started_at
        return (time.time() - last) > seconds
