# AnnalsChallenge tracker

Announces first accepted [lean-eval](https://github.com/leanprover/lean-eval)
solutions of AnnalsChallenge problems to a Zulip topic.

A scheduled GitHub Action runs `annals_zulip.py` every five minutes
(GitHub throttles frequent schedules, so runs can land later than that). The script
pulls the [results store](https://github.com/leanprover/lean-eval-submissions),
posts any first solves it hasn't announced before, and remembers them in
`state.json`, which the workflow commits back.
