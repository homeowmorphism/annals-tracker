# AnnalsChallenge tracker

Announces first accepted [lean-eval](https://github.com/leanprover/lean-eval)
solutions of AnnalsChallenge problems to one or more Zulip topics.

A scheduled GitHub Action runs `annals_zulip.py` every five minutes.
GitHub throttles frequent schedules, so runs can land later than that. The
script pulls the [results store](https://github.com/leanprover/lean-eval-submissions),
posts any first solves it hasn't announced before, and remembers them in
`state.json`, which the workflow commits back.

## Requirements

Python 3.9 or newer and `git`. The script uses only the standard library, so
there is nothing to install.

## Try it without any setup

`--dry-run` prints the message instead of posting it, and skips the
credential check entirely. Nothing here touches Zulip.

```sh
# What would be announced right now?
python3 annals_zulip.py --dry-run

# The full table of every first solve so far.
python3 annals_zulip.py --all --dry-run
```

The first run shallow-clones the submissions repo (about 2 MB) into
`~/.cache/annals-zulip`. Later runs just pull it.

The output is grouped by destination. With nothing configured the script
cannot tell which topic you mean, so it shows the full table. Once you have
configured one, a plain `--dry-run` usually reports `nothing new`, because
`state.json` already lists what that topic has seen. `--all` shows the full
table either way.

## Posting for real

The script needs five settings:

| Variable | What it is |
| --- | --- |
| `ZULIP_SITE` | Your Zulip organization's URL |
| `ZULIP_CHANNEL` | Channel to post in |
| `ZULIP_TOPIC` | Topic within that channel |
| `ZULIP_BOT_EMAIL` | The bot's email |
| `ZULIP_API_KEY` | The bot's API key |

To get the last two, open your Zulip settings, go to **Bots**, and add a
generic bot. Zulip shows its email and API key on the bot's card. Subscribe
the bot to the channel you want it to post in.

Run the script once from a terminal and it prompts for whatever is missing,
then saves all five to `~/.config/annals-zulip.env` with mode 600:

```sh
python3 annals_zulip.py
```

With the seeded `state.json` that ordinary run posts nothing, so it is a safe
way to check the credentials.

Real environment variables take precedence over that file, which is how the
GitHub Action supplies them. Export all five yourself if you prefer.

## Posting to more than one topic

`ZULIP_CHANNEL_2` and `ZULIP_TOPIC_2` add a second destination, `_3` a third,
and so on. The script stops looking at the first gap in the numbering.

```sh
export ZULIP_CHANNEL_2='a second channel'
export ZULIP_TOPIC_2='the topic within it'
python3 annals_zulip.py
```

A topic that `state.json` has not seen before gets the full table of every
first solve, and only new ones after that. Adding a destination catches it up
on its own; there is no separate seeding step.

Subscribe the bot to every channel you add.

## The 27th solve

By request, the announcement that carries the 27th solve opens with an extra
line in the **Formal Landmarks** channel, before the usual message:

> I have stopped the count on special request. Nah just kidding. The singularity takeover is incoming:

`GAG_CHANNEL`, `GAG_POSITION` and `GAG` near the top of the script control
it. Delete them and the two lines that use them once the joke has run.

## Starting a fresh tracker

A new topic is caught up with the full table by itself, which is usually what
you want. The two commands here cover the cases where it is not.

To announce nothing historical, record every current solve as already
announced. This writes an entry for each configured destination, so only
future solves get posted anywhere:

```sh
python3 annals_zulip.py --mark-announced
```

`--all` does the opposite. It posts the full table to every destination and
marks all of it announced, which is how to re-post the baseline to a topic
that already has one.

## Running it on GitHub Actions

1. Fork this repo.
2. Under **Settings → Secrets and variables → Actions**, add the five
   settings above as repository secrets, under the same names. Add
   `ZULIP_CHANNEL_2` and `ZULIP_TOPIC_2` as well for a second topic; the
   workflow already passes them through when they exist.
3. Open the **Actions** tab and enable workflows. Forks start with them
   disabled.
4. Run **AnnalsChallenge tracker** manually once from the Actions tab to
   check the credentials.

The workflow ([.github/workflows/tracker.yml](.github/workflows/tracker.yml))
needs `contents: write` so it can commit `state.json` back. That permission
is already declared in the file.

Two details in there are deliberate. The cron fires at `:02`, `:07`, `:12`
and so on rather than on the five-minute mark, because GitHub delays
scheduled runs most at the top of the hour. And the commit step makes an
empty commit if the repo has been quiet for 30 days, because GitHub disables
scheduled workflows on a public repo after 60 quiet days.

## How state works

`ANNALS_WORKDIR` decides where the script keeps its clone and its
`state.json`. It defaults to `~/.cache/annals-zulip`. The workflow sets it to
the checkout directory, so in CI `state.json` is the one committed at the
repo root.

To reproduce a CI run locally, point the script at this directory:

```sh
ANNALS_WORKDIR=$PWD python3 annals_zulip.py --dry-run
```

That clones the submissions repo into `lean-eval-submissions/` here, which
`.gitignore` already covers, and reads the committed `state.json`.

The file records, per destination, the issue number announced for each
problem.

Renaming a channel or topic produces a new key, and the renamed topic then
gets the full table again. Rename its key in `state.json` in the same commit
to avoid that.

## Commands

| Command | Effect |
| --- | --- |
| `annals_zulip.py` | Post the first solves each topic has not seen, then record them |
| `annals_zulip.py --all` | Post the full table to every topic, then record it |
| `annals_zulip.py --mark-announced` | Record current solves as announced everywhere, post nothing |
| `annals_zulip.py --dry-run` | Print instead of posting; needs no credentials |

`--dry-run` combines with `--all`. It never writes `state.json`.
