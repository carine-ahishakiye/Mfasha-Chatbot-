"""Register, update, deactivate or list the officers who sign in with phone number + PIN.

    python scripts/add_officer.py add --phone 0788123456 --name "Mukamana Jeanne"      (asks for the PIN)
    python scripts/add_officer.py add --phone 0788123456 --name "Mukamana Jeanne" --pin 4821
    python scripts/add_officer.py deactivate --phone 0788123456
    python scripts/add_officer.py activate --phone 0788123456
    python scripts/add_officer.py list

`add` on a phone number that already exists changes its name and PIN (use it to reset a forgotten PIN).
The script reads .env from the project folder so it uses the same database as the server."""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.split("  #")[0].strip().strip('"').strip("'"))


def main() -> int:
    load_env(ROOT / ".env")
    from mfasha.auth import normalize_phone, valid_pin
    from mfasha.config import Settings
    from mfasha.storage import InteractionRepository, create_session_factory

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["add", "deactivate", "activate", "list"])
    parser.add_argument("--phone")
    parser.add_argument("--name")
    parser.add_argument("--pin", help="4 to 6 digits. Leave it out to be asked without it showing on screen.")
    args = parser.parse_args()

    repo = InteractionRepository(create_session_factory(Settings.from_env().database_url))

    if args.action == "list":
        rows = repo.list_officers()
        for r in rows:
            print(f"{r['phone']:<15} {r['name']:<30} {'active' if r['active'] else 'DEACTIVATED'}")
        print(f"{len(rows)} officer(s)")
        return 0

    phone = normalize_phone(args.phone or "")
    if phone is None:
        print("error: give a valid --phone, for example 0788123456")
        return 1

    if args.action in ("activate", "deactivate"):
        if not repo.set_officer_active(phone, args.action == "activate"):
            print(f"error: no officer with phone {phone}")
            return 1
        print(f"{phone} {args.action}d")
        return 0

    name = (args.name or "").strip()
    if len(name) < 2:
        print("error: give the officer's --name")
        return 1
    pin = args.pin or getpass.getpass("PIN (4 to 6 digits): ")
    if not valid_pin(pin):
        print("error: the PIN must be 4 to 6 digits")
        return 1
    if not args.pin and getpass.getpass("Type the PIN again: ") != pin:
        print("error: the two PINs are different")
        return 1
    created = repo.upsert_officer(phone, name, pin)
    print(f"{'added' if created else 'updated'} {name} ({phone})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())