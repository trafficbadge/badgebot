"""One command for badgebot on your PC:   py bb.py <command>

    py bb.py printify-setup
    py bb.py printify-test 29622686
    py bb.py replay replays\\blueberry_405_2018.json
    py bb.py forget            (removes keys this PC remembered)

It goes to badgebot's folder, installs or updates what badgebot needs (only when that changed),
and asks for a key only when the command needs one. Keys can be remembered in Windows'
Credential Manager (encrypted for your Windows account), never in a file in this folder.
"""
import getpass
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "Scripts" if os.name == "nt" else "bin",
                       "python.exe" if os.name == "nt" else "python")
STAMP = os.path.join(HERE, ".venv", "installed.sha1")
SERVICE = "badgebot"

# Which keys each command needs (asked for only if not already set or remembered).
NEEDS = {
    "printify-setup": ["PRINTIFY_TOKEN"],
    "printify-test": ["PRINTIFY_TOKEN"],
}
# Email settings for test alerts from this PC (the password is asked for and can be remembered).
PC_EMAIL = {"SMTP_HOST": "mail.privateemail.com", "SMTP_PORT": "465", "SMTP_USER": "info@badtraffic206.com",
            "MAIL_FROM": "info@badtraffic206.com", "OWNER_EMAIL": "egrigg9000@gmail.com"}


def ask_hidden(label):
    """Paste-safe hidden prompt. On Windows it uses PowerShell's own secure prompt, because a
    plain Python prompt there can turn Ctrl+V into a control character instead of pasting."""
    if os.name == "nt":
        ps = (f"$s = Read-Host -AsSecureString '{label} (hidden; paste, then Enter)'; "
              "[System.Net.NetworkCredential]::new('', $s).Password")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.PIPE, text=True)
        value = r.stdout.strip()
    else:
        value = getpass.getpass(f"{label} (hidden as you paste, then Enter): ").strip()
    value = "".join(ch for ch in value if ch.isprintable())   # drop stray control characters
    print(f"   got {len(value)} characters")
    return value


def run(cmd):
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode:
        sys.exit(r.returncode)


def ensure_installed():
    req = open(os.path.join(HERE, "requirements.txt"), "rb").read() + b"keyring\n"
    want = hashlib.sha1(req).hexdigest()
    have = open(STAMP).read().strip() if os.path.exists(STAMP) else ""
    if not os.path.exists(VENV_PY):
        print("First run: setting up badgebot's parts (a few minutes)...")
        run([sys.executable, "-m", "venv", ".venv"])
    if want != have:
        print("Installing or updating badgebot's parts...")
        run([VENV_PY, "-m", "pip", "install", "-q", "-r", "requirements.txt", "keyring"])
        run([VENV_PY, "-m", "playwright", "install", "chromium"])
        with open(STAMP, "w") as f:
            f.write(want)


def inside(args):
    """Runs inside badgebot's own Python, where keyring is installed."""
    try:
        import keyring
    except ImportError:   # still works, just can't remember keys
        keyring = None
    if args[:1] == ["forget"] and keyring:
        for name in ["PRINTIFY_TOKEN", "SMTP_PASSWORD"]:
            try:
                keyring.delete_password(SERVICE, name)
                print("Forgot", name)
            except Exception:
                pass
        return
    env = dict(os.environ)
    needs = list(NEEDS.get(args[0] if args else "", []))
    if args[:1] == ["replay"]:
        for k, v in PC_EMAIL.items():
            env.setdefault(k, v)
        needs.append("SMTP_PASSWORD")
    for name in needs:
        if env.get(name):
            continue
        saved = keyring.get_password(SERVICE, name) if keyring else None
        if saved:
            env[name] = saved
            continue
        label = {"PRINTIFY_TOKEN": "Printify token", "SMTP_PASSWORD": "Namecheap app password"}.get(name, name)
        value = ask_hidden(label)
        if not value:
            sys.exit(f"No {label} entered.")
        env[name] = value
        if keyring and input("Remember it on this PC? (y/n): ").strip().lower().startswith("y"):
            keyring.set_password(SERVICE, name, value)
    sys.exit(subprocess.run([sys.executable, "-m", "badgebot", *args], cwd=HERE, env=env).returncode)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--inside"]:
        inside(sys.argv[2:])
    else:
        if len(sys.argv) < 2:
            sys.exit(__doc__)
        ensure_installed()
        sys.exit(subprocess.run([VENV_PY, os.path.abspath(__file__), "--inside", *sys.argv[1:]], cwd=HERE).returncode)
