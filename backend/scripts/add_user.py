"""Add or update a login.

    python -m scripts.add_user ana@critiore.ai --name "Ana" --role team
    python -m scripts.add_user client@miner.mn --role client --regions kharkhiraa
    python -m scripts.add_user someone@x.com --remove

Prompts for the password unless --password is given.
"""

import argparse
import getpass

from app.auth import hash_password, load_accounts, save_accounts, users_path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("email")
    p.add_argument("--name")
    p.add_argument("--role", choices=["team", "client"], default="team")
    p.add_argument("--regions", nargs="+", default=None, help="region ids a client may see (team sees all)")
    p.add_argument("--password")
    p.add_argument("--remove", action="store_true")
    a = p.parse_args()

    accounts = load_accounts()
    key = a.email.strip().lower()
    if a.remove:
        accounts.pop(key, None)
        save_accounts(accounts)
        print(f"Removed {key}")
        return
    if a.role == "client" and not a.regions:
        p.error("a client needs --regions")
    password = a.password or getpass.getpass(f"Password for {key}: ")
    if len(password) < 10:
        p.error("use a password of at least 10 characters")
    accounts[key] = {
        "email": key,
        "name": a.name or accounts.get(key, {}).get("name") or key,
        "role": a.role,
        "regions": a.regions or ["*"],
        "password_hash": hash_password(password),
    }
    save_accounts(accounts)
    print(f"Saved {key} ({a.role}) to {users_path()}")


if __name__ == "__main__":
    main()
