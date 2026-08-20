#!/usr/bin/env python3
"""Post first accepted lean-eval solutions of AnnalsChallenge problems to Zulip.

Each run pulls leanprover/lean-eval-submissions, computes the first accepted
submission for every annals_* problem, and announces the ones it hasn't
announced before. Announced solves are remembered per destination in a state
file, so the script is safe to run from cron.

ZULIP_SITE, ZULIP_CHANNEL, ZULIP_TOPIC, ZULIP_BOT_EMAIL, and ZULIP_API_KEY
come from the environment (e.g. GitHub Actions secrets) or from
~/.config/annals-zulip.env, which an interactive run offers to create.
ZULIP_CHANNEL_2 and ZULIP_TOPIC_2 (then _3, and so on) add more destinations.

Usage:
  annals_zulip.py                   announce new first solves
  annals_zulip.py --all             post the full table of first solves
  annals_zulip.py --mark-announced  record current solves as announced, post nothing
  annals_zulip.py --dry-run         print instead of posting (needs no credentials)
"""

import argparse
import base64
import getpass
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "https://github.com/leanprover/lean-eval-submissions.git"
ISSUES = "https://github.com/leanprover/lean-eval-submissions/issues"
MANIFESTS_API = "https://api.github.com/repos/leanprover/lean-eval/contents/manifests/problems"
WORKDIR = Path(os.environ.get("ANNALS_WORKDIR", Path.home() / ".cache" / "annals-zulip"))
CONFIG_PATH = Path.home() / ".config" / "annals-zulip.env"
REQUIRED = ["ZULIP_SITE", "ZULIP_CHANNEL", "ZULIP_TOPIC", "ZULIP_BOT_EMAIL", "ZULIP_API_KEY"]


def load_config(interactive=True):
    """Fill os.environ from the config file, prompting interactively for gaps.

    Real environment variables win over the file. All five settings are
    required to post; a dry run passes interactive=False and makes do with
    whatever happens to be set.
    """
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if not missing or not interactive:
        return
    if not sys.stdin.isatty():
        sys.exit(f"missing {', '.join(missing)}; set them in the environment or run once interactively")
    print(f"One-time setup; values are saved to {CONFIG_PATH}.")
    for k in missing:
        label = k.removeprefix("ZULIP_").replace("_", " ").lower()
        v = getpass.getpass(f"{label} (hidden): ") if k == "ZULIP_API_KEY" else input(f"{label}: ")
        os.environ[k] = v.strip()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text("".join(f"{k}={os.environ[k]}\n" for k in REQUIRED))
    CONFIG_PATH.chmod(0o600)


def destinations():
    """Every channel and topic to post to, in order.

    ZULIP_CHANNEL/ZULIP_TOPIC is the first; ZULIP_CHANNEL_2/ZULIP_TOPIC_2,
    then _3, and so on add more. A dry run without any configuration falls
    back to a placeholder, which has announced nothing and so shows the full
    table.
    """
    dests = [(os.environ.get("ZULIP_CHANNEL", "(unset)"), os.environ.get("ZULIP_TOPIC", "(unset)"))]
    n = 2
    while (channel := os.environ.get(f"ZULIP_CHANNEL_{n}")) and (topic := os.environ.get(f"ZULIP_TOPIC_{n}")):
        dests.append((channel, topic))
        n += 1
    return dests


def name(dest):
    """How a destination is labelled in the state file and in run output."""
    return f"{dest[0]} > {dest[1]}"


def read_state(path, primary):
    """Announced issue numbers per destination: {"channel > topic": {problem: issue}}."""
    if not path.exists():
        return {}
    state = json.loads(path.read_text())
    # Before the tracker posted to more than one topic, the file was a single
    # flat {problem: issue} map. That history belongs to the first destination.
    if any(isinstance(v, int) for v in state.values()):
        return {name(primary): state}
    return state


# One AnnalsChallenge theorem predates the Aug 2026 import under an
# unprefixed id; a solve of either problem settles the same target.
ALIASES = {"duffin_schaeffer": "annals_duffin_schaeffer_conjecture"}


def target(pid):
    return pid if pid.startswith("annals_") else ALIASES.get(pid)


def sync_repo() -> Path:
    repo = WORKDIR / "lean-eval-submissions"
    if repo.exists():
        subprocess.run(["git", "-C", str(repo), "pull", "-q"], check=True)
    else:
        WORKDIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, str(repo)], check=True)
    return repo


def first_solves(repo: Path) -> dict:
    """Earliest accepted submission per AnnalsChallenge target, ties broken by issue number."""
    best = {}
    for f in (repo / "results").glob("*.json"):
        data = json.loads(f.read_text())
        if data.get("schema_version") != 1:
            sys.exit(f"{f.name}: unexpected schema_version {data.get('schema_version')}")
        for model, probs in data["solved"].items():
            for pid, rec in probs.items():
                t = target(pid)
                if t is None:
                    continue
                key = (rec["solved_at"], rec["issue_number"])
                if t not in best or key < (best[t]["solved_at"], best[t]["issue"]):
                    best[t] = {
                        "solved_at": rec["solved_at"],
                        "issue": rec["issue_number"],
                        "model": model,
                        "user": data["user"],
                        "pid": pid,
                    }
    return best


def annals_total():
    """Number of annals_* problems on the benchmark, or None if the API is unreachable."""
    try:
        with urllib.request.urlopen(MANIFESTS_API, timeout=10) as r:
            entries = json.load(r)
        return sum(1 for e in entries if e["name"].startswith("annals_")) or None
    except Exception:
        return None


def line(n, t, rec):
    via = f" (via `{rec['pid']}`)" if rec["pid"] != t else ""
    return (
        f"{n}. `{t}`{via}: [#{rec['issue']}]({ISSUES}/{rec['issue']})"
        f" — {rec['model']} ({rec['user']}), {rec['solved_at'].replace('T', ' ').replace('Z', ' UTC')}"
    )


def post(content: str, channel: str, topic: str):
    site = os.environ["ZULIP_SITE"].rstrip("/")
    auth = f"{os.environ['ZULIP_BOT_EMAIL']}:{os.environ['ZULIP_API_KEY']}"
    body = urllib.parse.urlencode({
        "type": "stream",
        "to": channel,
        "topic": topic,
        "content": content,
    }).encode()
    req = urllib.request.Request(f"{site}/api/v1/messages", data=body)
    req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    if resp.get("result") != "success":
        sys.exit(f"Zulip rejected the message: {resp}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true", help="post the full table, not just new solves")
    ap.add_argument("--mark-announced", action="store_true",
                    help="record current solves as announced without posting")
    ap.add_argument("--dry-run", action="store_true", help="print instead of posting")
    args = ap.parse_args()

    load_config(interactive=not args.dry_run)
    dests = destinations()
    solves = first_solves(sync_repo())
    state_path = WORKDIR / "state.json"
    state = read_state(state_path, dests[0])

    if args.mark_announced:
        for d in dests:
            state[name(d)] = {p: solves[p]["issue"] for p in solves}
        state_path.write_text(json.dumps(state, indent=1, sort_keys=True))
        print(f"marked {len(solves)} solves as announced for {len(dests)} destination(s); nothing posted")
        return

    total = annals_total()
    denom = f"/{total}" if total else ""
    # Number by position in the overall solve order, so an announcement of the
    # 15th solve says 15 rather than restarting at 1.
    order = sorted(solves, key=lambda p: (solves[p]["solved_at"], solves[p]["issue"]))
    position = {p: i for i, p in enumerate(order, 1)}

    posted = False
    for d in dests:
        announced = state.get(name(d))
        # A destination the state file has never heard of is caught up with the
        # full table, so adding one posts the backlog once and new solves after.
        if args.all or announced is None:
            rows = dict(solves)
            header = f"First accepted submission per solved AnnalsChallenge problem ({len(solves)}{denom}):"
        else:
            rows = {p: r for p, r in solves.items() if p not in announced}
            plural = "s" if len(rows) > 1 else ""
            header = f"New AnnalsChallenge first solve{plural} ({len(solves)}{denom} now solved):"
        if not rows:
            if args.dry_run:
                print(f"[{name(d)}] nothing new")
            continue
        content = "\n".join([header] + [line(position[p], p, rows[p]) for p in order if p in rows])
        if args.dry_run:
            print(f"[{name(d)}]\n{content}")
            continue
        post(content, *d)
        state[name(d)] = {**(announced or {}), **{p: rows[p]["issue"] for p in rows}}
        posted = True
        print(f"posted {len(rows)} solve(s) to {name(d)}")
    if posted:
        state_path.write_text(json.dumps(state, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
