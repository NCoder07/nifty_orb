"""
One-time helper: stores your Angel One SmartAPI credentials as environment
variables so the algo can log in. Nothing is written to any file.

    python setup_credentials.py

After it finishes, CLOSE this terminal and open a new one.
"""

import getpass
import platform
import subprocess
import sys

FIELDS = [
    ("ANGEL_API_KEY", "SmartAPI API key (from smartapi.angelbroking.com, app type Trading API)"),
    ("ANGEL_CLIENT_CODE", "Angel One client code (e.g. A123456)"),
    ("ANGEL_MPIN", "4-digit MPIN used in the Angel One app"),
    ("ANGEL_TOTP_SECRET", "TOTP secret text shown under the QR code when enabling TOTP (~26 chars)"),
]


def main():
    print("Angel One SmartAPI credential setup. Typing is hidden; paste and press Enter.\n")
    values = {}
    for name, prompt in FIELDS:
        while True:
            v = getpass.getpass(f"{prompt}\n  {name}: ").strip()
            if v:
                break
            print("  value cannot be empty")
        values[name] = v

    if values["ANGEL_TOTP_SECRET"].isdigit() and len(values["ANGEL_TOTP_SECRET"]) == 6:
        print("\nWARNING: that looks like a 6-digit code, not the secret. "
              "The secret is the long text under the QR code.")

    if platform.system() == "Windows":
        for name, v in values.items():
            r = subprocess.run(["setx", name, v], capture_output=True, text=True)
            status = "saved" if r.returncode == 0 else f"FAILED: {r.stderr.strip()}"
            print(f"  {name}: {status}")
        print("\nDone. Close this window, open a NEW PowerShell window, then run:\n"
              "    python angel_login.py")
    else:
        rc = "~/.zshrc" if "zsh" in (subprocess.os.environ.get("SHELL") or "") else "~/.bashrc"
        print(f"\nAdd these lines to {rc}, then open a new terminal:\n")
        for name, v in values.items():
            print(f'export {name}="{v}"')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\ncancelled")
