=====================================================================
 NIFTY OPENING RANGE BREAKOUT (ORB) ALGO  -  Angel One SmartAPI
=====================================================================

This package is a complete, ready-to-run trading algorithm. Follow the
steps in order. Nothing here needs code changes; all settings live in
config.py and all credentials live in your computer's environment
variables (never inside the code).

CONTENTS
  1. What the strategy does
  2. What you need before starting
  3. Install Python and the libraries
  4. Get your Angel One SmartAPI credentials
  5. Add your credentials to the computer
  6. Test the login
  7. Configure the algo (config.py)
  8. Replay on past data (optional but recommended)
  9. Run the algo
 10. Understanding the screen output
 11. Files in this package
 12. Going live: checklist and warnings
 13. Troubleshooting


---------------------------------------------------------------------
 1. WHAT THE STRATEGY DOES
---------------------------------------------------------------------
Instrument : Nifty 50 index on 5-minute candles (or a single stock).
Timeframe  : Intraday only. Everything is closed by 15:10.

Rules
  a) Opening range = the HIGH and LOW of the six 5-minute candles from
     09:15 to 09:45.
  b) From the 09:45 candle until the candle that closes at 12:10, the
     first candle that CLOSES above the range high gives a LONG entry.
     The first candle that CLOSES below the range low gives a SHORT.
     Entry is a market order the moment that candle closes.
  c) Stop loss = the LOW of the candle just before the breakout candle
     (for a long) or its HIGH (for a short).
     Example: the 11:10 candle closes above the range high. Entry at
     11:15 (close of the 11:10 candle). Stop = low of the 11:05 candle.
  d) Target = entry + 4 x (entry - stop) for a long, mirrored for a
     short. The 4 is RISK_REWARD in config.py. Target is checked on
     every live tick and exits immediately when touched.
  e) The stop loss is only honoured if a candle CLOSES beyond it.
     A wick through the stop is ignored. This avoids fake stop-outs.
  f) No signal by 12:10 = no trade that day.
  g) Any position still open at 15:10 is closed at market.
  h) One completed trade per day by default (MAX_TRADES_PER_DAY).

Two modes
  FUTURES : signals on the Nifty 50 index, orders on the current-month
            Nifty futures contract (rolls to next month automatically
            when expiry is within 2 days). Size = LOTS.
  STOCK   : signals and orders on one stock, e.g. RELIANCE. Size =
            STOCK_CAPITAL x STOCK_LEVERAGE / price.

Paper vs live
  PAPER_TRADING = True  : every step runs exactly the same, but orders
                          are simulated at the live price. No money.
  PAPER_TRADING = False : real orders are sent to your Angel One account.


---------------------------------------------------------------------
 2. WHAT YOU NEED BEFORE STARTING
---------------------------------------------------------------------
  * An Angel One trading account with the F&O segment activated
    (needed for Nifty futures; stocks only need the equity segment).
  * Windows 10/11 or Windows Server. (Mac/Linux also work; see notes.)
  * Python 3.11 (3.10 to 3.12 are fine).
  * A stable internet connection. The algo runs all day.
  * The computer must stay ON with the terminal window open during
    market hours. A small cloud VM or an always-on PC is ideal.


---------------------------------------------------------------------
 3. INSTALL PYTHON AND THE LIBRARIES
---------------------------------------------------------------------
  1. Download Python 3.11 from https://www.python.org/downloads/
     During install, TICK "Add python.exe to PATH". This matters.
  2. Unzip this package into a folder WITHOUT special characters,
     for example:  C:\algo\nifty_orb
  3. Open PowerShell (Start menu, type "PowerShell") and run:

        cd C:\algo\nifty_orb
        python --version
        pip install -r requirements.txt

     The last command installs these libraries:
        smartapi-python   Angel One's official SDK
        pyotp             generates the 6-digit TOTP for login
        logzero           needed by the SDK (it does not install it itself)
        websocket-client  live price stream

  If "python" is not recognised, Python was installed without PATH.
  Reinstall it and tick the PATH box.


---------------------------------------------------------------------
 4. GET YOUR ANGEL ONE SMARTAPI CREDENTIALS
---------------------------------------------------------------------
You need FOUR things. Collect them all before the next step.

  A) API KEY
     1. Go to https://smartapi.angelbroking.com and sign up with your
        Angel One client details.
     2. Click "Create an app". Choose app type "Trading API"
        (the other types cannot place orders).
     3. App name: anything. Redirect URL: http://127.0.0.1
     4. Copy the API Key shown (about 8 characters).

  B) CLIENT CODE
     Your Angel One account ID, e.g. A123456. It is on the Angel One
     app profile page.

  C) MPIN
     The 4-digit PIN you use to log in to the Angel One app.

  D) TOTP SECRET
     1. On the SmartAPI site, click "Enable TOTP" (top menu).
     2. Enter client code and PIN, verify with the OTP sent to you.
     3. A QR code appears WITH A TEXT SECRET under it (about 26
        characters, letters and digits). Copy that text. This is the
        secret; the algo uses it to generate a fresh 6-digit code on
        every login so you never type an OTP by hand.

  Also on the SmartAPI portal, check that your Trading API app shows
  as active and that you have accepted the algo-trading consent.


---------------------------------------------------------------------
 5. ADD YOUR CREDENTIALS TO THE COMPUTER
---------------------------------------------------------------------
Credentials are stored as Windows environment variables, not in any
file. The easiest way is the helper script:

        python setup_credentials.py

It asks for the four values (typing is hidden) and saves them. Then
CLOSE the PowerShell window and open a NEW one. New variables are only
visible to programs started after they were saved.

Manual alternative (PowerShell, one line each, use your own values):

        setx ANGEL_API_KEY      "your_api_key"
        setx ANGEL_CLIENT_CODE  "A123456"
        setx ANGEL_MPIN         "1234"
        setx ANGEL_TOTP_SECRET  "your_26_char_secret"

Mac / Linux: add these lines to ~/.bashrc or ~/.zshrc and open a new
terminal:

        export ANGEL_API_KEY="your_api_key"
        export ANGEL_CLIENT_CODE="A123456"
        export ANGEL_MPIN="1234"
        export ANGEL_TOTP_SECRET="your_26_char_secret"

Never share these four values with anyone and never paste them into
config.py or any other file.


---------------------------------------------------------------------
 6. TEST THE LOGIN
---------------------------------------------------------------------
In the NEW PowerShell window:

        cd C:\algo\nifty_orb
        python angel_login.py

Success looks like:

        Login OK
          Client   : A1********
          Exchanges: nse_fo, nse_cm, ...
          Products : MARGIN, MIS, NRML, CNC, ...
          Login at : 2026-09-25T08:55:03

Your client code is deliberately masked. If it says a variable is
missing, you skipped step 5 or did not open a new window. If it says
invalid TOTP, sync your computer clock (Settings > Time > Sync now).


---------------------------------------------------------------------
 7. CONFIGURE THE ALGO  (config.py)
---------------------------------------------------------------------
Open config.py in Notepad. The important lines:

  PAPER_TRADING = True      Keep True until you have watched the algo
                            for several days. False = real money.
  INSTRUMENT = "FUTURES"    or "STOCK"
  STOCK_SYMBOL = "RELIANCE" Only used in STOCK mode. Capital letters.
  LOTS = 1                  Futures lots per trade (1 lot = 65 Nifty).
  STOCK_CAPITAL = 100000    Rupees per stock trade, before leverage.
  STOCK_LEVERAGE = 5        Intraday leverage for stocks.
  RISK_REWARD = 4           Target distance = 4 x stop distance.
  MAX_TRADES_PER_DAY = 1    Set 2 or more to allow re-entry after a stop.
  RANGE_START = "09:15"     First candle of the opening range.
  RANGE_END = "09:45"       Range is complete when this candle closes.
  ENTRY_WINDOW_END = "12:10"  Last candle CLOSE time that may enter.
  SQUARE_OFF_TIME = "15:10" Everything closed at this time.
  HOLIDAYS = [ ]            Add NSE holidays as "YYYY-MM-DD" strings.

Save the file. The algo reads it at every start.


---------------------------------------------------------------------
 8. REPLAY ON PAST DATA  (optional but recommended)
---------------------------------------------------------------------
        python replay.py 30

Runs the exact same strategy engine over the last 30 calendar days of
real 5-minute candles and prints every trade plus a summary. Use it to
check that the rules behave as you expect before running live. Note:
replay has no tick data, so a target counts as hit when a candle's high
or low reaches it, and P&L is in Nifty points x quantity.


---------------------------------------------------------------------
 9. RUN THE ALGO
---------------------------------------------------------------------
        python main.py

or double-click run.bat. Leave the window open. The algo:

  * Sleeps until 08:55 on the next trading day (weekends and listed
    holidays are skipped automatically).
  * At 08:55 logs in, downloads the day's instrument list, picks the
    correct futures contract, connects the live price feed.
  * From 09:15 fetches each 5-minute candle a few seconds after it
    closes and applies the rules.
  * Exits at target on the live tick, at stop on a candle close, or at
    15:10 at the latest.
  * After 15:31 (or as soon as the day's trade is done) goes back to
    sleep until the next session. It runs like this 24/7.

Stop it with Ctrl+C. Start it again with the same command. It saves
its state after every event, so if it is restarted in the middle of a
day it remembers the range and any open position.

Only one copy may run at a time. Starting main.py automatically stops
any older copy that is still running in the background (closing a
terminal window does not always end the process). You will see
"stopped an older copy of the algo" when that happens.

Every completed trade is appended to trades.csv. Daily logs are in the
logs folder.


---------------------------------------------------------------------
 10. UNDERSTANDING THE SCREEN OUTPUT
---------------------------------------------------------------------
  candle 09:40 O ... C ...  -> opening range set: high X low Y
        The range is ready. Now waiting for a breakout close.

  SIGNAL LONG breakout: close 23150 beyond range, SL 23120, target 23270
  [PAPER] LONG ENTRY NIFTY27OCT26FUT x65 @ 23180 | spot 23150 | ...
        Entry taken. [PAPER] means simulated, [LIVE] means a real order.

  [PAPER] LONG EXIT (TARGET) ... points +90 | P&L +5850
        Exit reason is TARGET, STOP_LOSS or SQUARE_OFF.

  MISSED SHORT breakout at 11:55 (algo was not running)
        A breakout happened while the algo was off. It will not enter
        late at a worse price.

  nothing more to do today
        Either the trade for the day is finished or 12:10 passed with
        no signal.

  candle fetch attempt 3 raised ... exceeding access rate
        Angel's server throttled the request. The algo retries by
        itself; only repeated warnings are a concern.


---------------------------------------------------------------------
 11. FILES IN THIS PACKAGE
---------------------------------------------------------------------
  README.txt            This guide.
  CHANGELOG.txt         What changed in each version.
  VERSION.txt           Version number of this package.
  requirements.txt      Library list for pip.
  run.bat               Double-click launcher for Windows.
  setup_credentials.py  One-time helper to store your four credentials.
  config.py             ALL settings. The only file you normally edit.
  main.py               The 24/7 runner. Start this.
  replay.py             Replays the strategy on past candles.
  angel_login.py        Automatic login with TOTP; reuses the day's session.
  strategy.py           The strategy rules. Pure logic, no network calls.
  market_data.py        Candle download, live tick feed.
  instruments.py        Finds the Nifty index, futures and stock tokens.
  broker.py             Order placement: paper simulation and live orders.
  .gitignore            Keeps secrets and logs out of version control.

  Created while running (not in the zip):
  .session.json         Today's login tokens. Delete if you like.
  scrip_master.json     Instrument list, re-downloaded daily.
  state/                Per-day state for restart safety.
  logs/                 Daily log files.
  trades.csv            Your trade history.


---------------------------------------------------------------------
 12. GOING LIVE: CHECKLIST AND WARNINGS
---------------------------------------------------------------------
  [ ] Ran in paper mode for at least a week and compared the log with
      the chart every day.
  [ ] F&O segment is active and there is enough margin for one Nifty
      futures lot (roughly 1.5 lakh; check the Angel One margin page).
  [ ] LOTS = 1 for the first live days.
  [ ] Computer clock is synced and the internet is stable.
  [ ] You are at the terminal for the first live trade.
  [ ] You know how to close a position manually in the Angel One app
      if the algo or the internet fails.

  This is real money. Past replay results do not guarantee future
  results. The authors take no responsibility for trading losses.
  If the algo prints "session ended with an OPEN position", check the
  Angel One app immediately.


---------------------------------------------------------------------
 13. TROUBLESHOOTING
---------------------------------------------------------------------
  "Missing environment variables: ANGEL_..."
      Step 5 not done, or you did not open a NEW PowerShell window.

  "Invalid totp" / "Invalid Token" at login
      Sync the Windows clock. Check the TOTP secret is the 26-char text,
      not the 6-digit code. Check MPIN is the app PIN, not a password.

  "ModuleNotFoundError: No module named 'SmartApi'" (or logzero)
      Run: pip install -r requirements.txt

  "no market data by 09:35; treating today as a holiday"
      The exchange is closed today, or the internet was down at open.

  Login works but no ticks / "restarting tick feed"
      Firewall or proxy blocking websockets. Try another network.

  The futures symbol looks wrong
      The algo picks the nearest expiry at least FUT_ROLLOVER_DAYS away.
      The banner at 08:55 shows the exact contract every day.

  Two sessions at once
      Angel One allows one API session per client. Do not run the algo
      on two computers, and do not log in to another API tool at the
      same time, or one of them will be logged out.
