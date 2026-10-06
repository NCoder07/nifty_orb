"""Order execution. PaperBroker simulates fills at the live LTP; LiveBroker sends real orders."""

import datetime as dt
import logging
import time
from dataclasses import dataclass

import config
from instruments import Instrument

log = logging.getLogger("broker")


@dataclass
class Fill:
    price: float
    order_id: str
    time: dt.datetime


class PaperBroker:
    name = "PAPER"

    def __init__(self, feed, tz=None):
        self._feed = feed
        self._tz = tz
        self._count = 0

    def market_order(self, inst: Instrument, side: str, qty: int) -> Fill:
        price = self._feed.ltp(inst.token)
        if price is None:
            raise RuntimeError(f"no live price for {inst.symbol}; cannot simulate fill")
        self._count += 1
        return Fill(price, f"PAPER-{self._count}", dt.datetime.now(self._tz))


class LiveBroker:
    name = "LIVE"

    def __init__(self, api, feed, tz=None):
        self._api = api
        self._feed = feed
        self._tz = tz

    def market_order(self, inst: Instrument, side: str, qty: int) -> Fill:
        params = {
            "variety": "NORMAL",
            "tradingsymbol": inst.symbol,
            "symboltoken": inst.token,
            "transactiontype": side,           # BUY or SELL
            "exchange": inst.exchange,
            "ordertype": "MARKET",
            "producttype": config.PRODUCT_TYPE,
            "duration": "DAY",
            "price": "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(qty),
        }
        resp = self._api.placeOrderFullResponse(params)
        if not resp or not resp.get("status"):
            msg = (resp or {}).get("message", "no response")
            raise RuntimeError(f"order rejected by broker: {msg}")
        order_id = str(resp["data"]["orderid"])
        log.info("order %s sent: %s %d x %s", order_id, side, qty, inst.symbol)
        return self._wait_for_fill(order_id)

    def _wait_for_fill(self, order_id: str) -> Fill:
        deadline = time.time() + config.ORDER_FILL_TIMEOUT
        last_status = "unknown"
        while time.time() < deadline:
            try:
                book = self._api.orderBook()
            except Exception as exc:
                log.warning("order book fetch failed: %s", exc)
                book = None
            for row in ((book or {}).get("data") or []):
                if str(row.get("orderid")) != order_id:
                    continue
                last_status = str(row.get("status") or row.get("orderstatus") or "").lower()
                if last_status == "complete":
                    price = float(row.get("averageprice") or 0)
                    if price <= 0:
                        price = self._feed.ltp(str(row.get("symboltoken"))) or 0.0
                    return Fill(price, order_id, dt.datetime.now(self._tz))
                if last_status in ("rejected", "cancelled"):
                    raise RuntimeError(f"order {order_id} {last_status}: {row.get('text', '')}")
            time.sleep(1)
        raise RuntimeError(f"order {order_id} not filled within timeout (last status: {last_status})")
