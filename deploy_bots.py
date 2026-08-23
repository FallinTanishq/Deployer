#!/usr/bin/env python3
"""
Clone, set up and launch all bots on the VPS.

  export GITHUB_TOKEN=ghp_xxx
  python3 deploy_bots.py [--token ghp_xxx] [--only S...] [--skip S...]
                        [--base-dir DIR] [--no-apt] [--no-start]

Per bot: git clone/pull -> venv -> install reqs (+extras) -> tmux session.
Run on the Linux VPS. Attach with: tmux attach -t <session>
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

GITHUB_USER = "FallinTanishq"

BOTS = [
    {"name": "1080p-enc", "session": "1080p", "repo": "GoatEncoder", "branch": "1080p",
     "start": "python bot.py", "apt": ["ffmpeg"]},
    {"name": "480p-enc",  "session": "480p",  "repo": "GoatEncoder", "branch": "480p",
     "start": "python bot.py", "apt": ["ffmpeg"]},
    {"name": "720p-enc",  "session": "720p",  "repo": "GoatEncoder", "branch": "720p",
     "start": "python bot.py", "apt": ["ffmpeg"]},

    {"name": "AutoAniMovie",   "session": "animovie", "repo": "AutoAniMovie",    "start": "python bot.py"},
    {"name": "AutoCorn",       "session": "corn",     "repo": "AutoCorn",        "start": "python bot.py"},
    {"name": "AutoManga",      "session": "manga",    "repo": "AutoManga",       "start": "python bot.py"},
    {"name": "Auto-Ongoing",   "session": "ongoing",  "repo": "Auto-Ongoing",    "start": "python bot.py"},
    {"name": "AutoSeries",     "session": "series",   "repo": "AutoSeries",      "start": "python bot.py"},
    {"name": "FileSequence",   "session": "sequence", "repo": "FileSequence",    "start": "python bot.py"},
    {"name": "RequestAcceptor","session": "request",  "repo": "RequestAcceptor", "start": "python bot.py"},
    {"name": "AutoNews",       "session": "news",     "repo": "AutoNews",        "start": "python bot.py",
     "extra_pip": ["pillow"]},

    {"name": "infinite-copy",  "session": "copy",  "repo": "infinite-copy",  "start": "python3 main.py",
     "extra_pip": ["requests", "pytz", "motor"]},
    {"name": "infinite-links", "session": "links", "repo": "infinite-links", "start": "python3 main.py",
     "extra_pip": ["requests", "pytz", "motor"]},
    {"name": "infinite-mithu", "session": "mithu", "repo": "infinite-mithu", "start": "python3 main.py",
     "extra_pip": ["requests", "pytz", "motor"]},
    {"name": "infinite-nakul", "session": "nakul", "repo": "infinite-nakul", "start": "python3 main.py",
     "extra_pip": ["requests", "pytz", "motor"]},
    {"name": "infinite-stop",  "session": "stop",  "repo": "infinite-stop",  "start": "python3 main.py",
     "extra_pip": ["requests", "pytz", "motor"]},

    {"name": "TZML", "session": "tzml", "repo": "TZML", "start": "bash start.sh",
     "req_files": ["requirements.txt", "requirements-cli.txt"],
     "apt": ["ffmpeg", "mediainfo", "aria2", "qbittorrent-nox", "p7zip-full"]},
]

BASE_APT = ["git", "tmux", "python3-venv", "python3-pip", "curl"]


class C:
    G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[94m"; DIM = "\033[2m"; END = "\033[0m"


def log(msg, color=C.B):
    print(f"{color}==>{C.END} {msg}", flush=True)


def warn(msg):
    print(f"{C.Y}[warn]{C.END} {msg}", flush=True)


def err(msg):
    print(f"{C.R}[error]{C.END} {msg}", flush=True)


def run(cmd, cwd=None, check=True, quiet=False):
    shell = isinstance(cmd, str)
    if not quiet:
        print(f"{C.DIM}   $ {cmd if shell else ' '.join(cmd)}{C.END}", flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check, shell=shell)


def have(binary):
    return shutil.which(binary) is not None


def install_apt(packages):
    if not packages:
        return
    if not have("apt-get"):
        warn(f"apt-get not found; install manually: {', '.join(packages)}")
        return
    sudo = [] if os.geteuid() == 0 else ["sudo"]
    log(f"Installing system packages: {', '.join(packages)}")
    try:
        run(sudo + ["apt-get", "update", "-y"])
        run(sudo + ["apt-get", "install", "-y", *packages])
    except subprocess.CalledProcessError:
        warn(f"apt install failed for: {', '.join(packages)} (continuing)")


def clone_or_update(bot, base_dir, token):
    dest = base_dir / bot["name"]
    branch = bot.get("branch")
    auth_url = f"https://{token}@github.com/{GITHUB_USER}/{bot['repo']}.git"

    if (dest / ".git").exists():
        log(f"[{bot['name']}] repo exists -> pulling")
        if branch:
            run(["git", "checkout", branch], cwd=dest, check=False)
        run(["git", "pull", "--ff-only"], cwd=dest, check=False)
        return dest

    log(f"[{bot['name']}] cloning {GITHUB_USER}/{bot['repo']}" + (f" @ {branch}" if branch else ""))
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch, "--single-branch"]
    cmd += [auth_url, str(dest)]
    run(cmd, quiet=True)
    return dest


def make_venv(dest):
    venv = dest / "venv"
    if (venv / "bin" / "python").exists():
        log("venv exists -> reuse")
        return venv
    log("creating venv")
    run([sys.executable, "-m", "venv", str(venv)])
    return venv


def pip_install(bot, dest, venv):
    pip = str(venv / "bin" / "pip")
    log("upgrading pip / setuptools / wheel")
    run([pip, "install", "--upgrade", "pip", "setuptools", "wheel"], check=False)
    for rf in bot.get("req_files", ["requirements.txt"]):
        if (dest / rf).exists():
            log(f"installing {rf}")
            run([pip, "install", "-r", str(dest / rf)], check=False)
        else:
            warn(f"[{bot['name']}] {rf} not found, skipping")
    extra = bot.get("extra_pip", [])
    if extra:
        log(f"installing extra deps: {', '.join(extra)}")
        run([pip, "install", *extra], check=False)


def start_tmux(bot, dest):
    session = bot["session"]
    run(["tmux", "kill-session", "-t", session], check=False, quiet=True)
    run(["tmux", "new-session", "-d", "-s", session], check=True)
    inner = f"cd '{dest}' && source venv/bin/activate && {bot['start']}"
    run(["tmux", "send-keys", "-t", session, inner, "C-m"], check=True)
    log(f"[{bot['name']}] started in tmux session '{session}'  ({bot['start']})", C.G)


def main():
    ap = argparse.ArgumentParser(description="Clone, set up and launch all bots on the VPS.")
    ap.add_argument("--token", help="GitHub PAT (else uses $GITHUB_TOKEN)")
    ap.add_argument("--base-dir", default=str(Path.home()), help="clone location (default: home dir)")
    ap.add_argument("--only", nargs="+", metavar="S", help="only these (session or folder name)")
    ap.add_argument("--skip", nargs="+", metavar="S", help="skip these (session or folder name)")
    ap.add_argument("--no-apt", action="store_true", help="skip system packages")
    ap.add_argument("--no-start", action="store_true", help="set up but don't launch tmux")
    args = ap.parse_args()

    if sys.platform == "win32":
        err("Run this on the Linux VPS (needs tmux/venv/apt), not Windows.")
        sys.exit(1)

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        err("No GitHub token. Set $GITHUB_TOKEN or pass --token ghp_xxx")
        sys.exit(1)

    if not args.no_start and not have("tmux") and args.no_apt:
        err("tmux not installed and --no-apt given. Install tmux first.")
        sys.exit(1)

    base_dir = Path(args.base_dir).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)

    def selected(bot):
        keys = {bot["session"], bot["name"]}
        if args.only:
            return bool(keys & set(args.only))
        if args.skip:
            return not (keys & set(args.skip))
        return True

    bots = [b for b in BOTS if selected(b)]
    if not bots:
        err("No bots selected.")
        sys.exit(1)

    if not args.no_apt:
        apt = list(dict.fromkeys(BASE_APT + [p for b in bots for p in b.get("apt", [])]))
        install_apt(apt)

    results = []
    for bot in bots:
        print()
        log(f"===== {bot['name']}  (session: {bot['session']}) =====", C.B)
        try:
            dest = clone_or_update(bot, base_dir, token)
            venv = make_venv(dest)
            pip_install(bot, dest, venv)
            if args.no_start:
                results.append((bot, "set up (not started)"))
            else:
                start_tmux(bot, dest)
                results.append((bot, "running"))
        except subprocess.CalledProcessError as e:
            err(f"[{bot['name']}] failed: {e}")
            results.append((bot, "FAILED"))
        except Exception as e:
            err(f"[{bot['name']}] unexpected error: {e}")
            results.append((bot, "FAILED"))

    print("\n" + "=" * 60)
    log("Summary", C.B)
    for bot, status in results:
        color = C.G if status == "running" else (C.R if status == "FAILED" else C.Y)
        print(f"  {color}{status:<22}{C.END} {bot['name']:<16} tmux: {bot['session']}")
    print("=" * 60)
    print("\nAttach:  tmux attach -t <session>   (detach: Ctrl-b then d)")
    print("List:    tmux ls")
    print(f"Cloned:  {base_dir}")

    if any(s == "FAILED" for _, s in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
