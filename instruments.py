"""Instrument master download and token lookup for Angel One."""

import datetime as dt
import json
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import config

log = logging.getLogger("instruments")

MASTER_URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
CACHE = Path(__file__).with_name("scrip_master.json")

# Exchange codes used by the WebSocket feed.
WS_EXCHANGE = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5}


@dataclass
class Instrument:
    exchange: str        # "NSE" or "NFO"
    token: str
    symbol: str          # trading symbol, e.g. NIFTY27OCT26FUT or RELIANCE-EQ
    name: str
    lot_size: int
    expiry: Optional[dt.date] = None

    @property
    def ws_exchange(self) -> int:
        return WS_EXCHANGE[self.exchange]

    def __str__(self):
        return f"{self.symbol} ({self.exchange}:{self.token})"


def load_master(force: bool = False) -> list:
    """Return the scrip master, downloading it once per day."""
    if not force and CACHE.exists():
        cached_day = dt.date.fromtimestamp(CACHE.stat().st_mtime)
        if cached_day == dt.date.today():
            return json.loads(CACHE.read_text())
    log.info("downloading instrument master")
    raw = urllib.request.urlopen(MASTER_URL, timeout=120).read()
    CACHE.write_bytes(raw)
    return json.loads(raw)


def _row_to_instrument(row: dict) -> Instrument:
    expiry = None
    if row.get("expiry"):
        expiry = dt.datetime.strptime(row["expiry"], "%d%b%Y").date()
    return Instrument(
        exchange=row["exch_seg"],
        token=str(row["token"]),
        symbol=row["symbol"],
        name=row["name"],
        lot_size=int(row.get("lotsize") or 1),
        expiry=expiry,
    )


def nifty_index(master: list) -> Instrument:
    for row in master:
        if row["exch_seg"] == "NSE" and row["symbol"] == "Nifty 50":
            return _row_to_instrument(row)
    raise LookupError("Nifty 50 index not found in instrument master")


def nifty_future(master: list, today: dt.date) -> Instrument:
    """Nearest NIFTY future whose expiry is at least FUT_ROLLOVER_DAYS away."""
    rows = [r for r in master
            if r["exch_seg"] == "NFO" and r["name"] == "NIFTY" and r["instrumenttype"] == "FUTIDX"]
    futs = sorted((_row_to_instrument(r) for r in rows), key=lambda i: i.expiry)
    cutoff = today + dt.timedelta(days=config.FUT_ROLLOVER_DAYS)
    for f in futs:
        if f.expiry >= cutoff:
            return f
    raise LookupError("no NIFTY future found beyond the rollover cutoff")


def stock(master: list, symbol: str) -> Instrument:
    want = f"{symbol.upper()}-EQ"
    for row in master:
        if row["exch_seg"] == "NSE" and row["symbol"] == want:
            return _row_to_instrument(row)
    raise LookupError(f"stock {want} not found in instrument master")


def resolve(master: list, today: dt.date):
    """
    Return (signal_instrument, trade_instrument) for the configured mode.
    Signals are computed on the first; orders are placed on the second.
    """
    mode = config.INSTRUMENT.upper()
    if mode == "FUTURES":
        return nifty_index(master), nifty_future(master, today)
    if mode == "STOCK":
        s = stock(master, config.STOCK_SYMBOL)
        return s, s
    raise ValueError(f"config.INSTRUMENT must be FUTURES or STOCK, got {config.INSTRUMENT!r}")
