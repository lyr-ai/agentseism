# Coding-agent execution representation — `coding/1`

Frozen 2026-09-06, before any multi-task coding experiment. Derived from four
Sonnet runs on `astropy__astropy-12907` (SWE-bench Verified), one of which was
instrumented.

## Why this exists

On GAIA the declared features were free text — an initial plan, an evidence set,
a reasoning turn — and no two runs ever produced the same value, so nothing could
be conditioned against anything. On OpenRCA the features were better but still
required reading the agent's stated intent to decide what a step *meant*.

A coding agent acts on a repository, and a repository has a state that can be
hashed. That makes the representation below derivable without interpreting a
single word the model wrote.

## The representation

    Action        syntactic command signature
    State         canonical repository fingerprint, two levels
    Transition    source_changed / workspace_changed
    Outcome       final patch fingerprint, test result, exit status

### Action — syntax only

The executable of the first non-`cd` shell segment, plus syntactic markers found
in the string: `heredoc`, `redirect`, `append`, and literal flags.

    cat:heredoc,redirect     cat > file <<'EOF'
    cat                      cat file
    python:pytest            python -m pytest ...
    sed:-i                   sed -i ...

`cat` is both the read and the write here, separated only by a redirection, which
is why the first token is not enough — it reported 35 reads and zero writes on a
run that wrote eleven times. No intent is inferred: `heredoc` and `redirect` are
characters in the command.

### State — two fingerprints, deliberately

    tracked_diff_hash      sha256 of `git diff HEAD`      -- the source
    workspace_diff_hash    tracked diff + untracked file contents
    changed_files          `git diff --name-only HEAD`
    untracked_files        `git ls-files --others --exclude-standard`

Both, because the boundary is not obvious in advance: in the validation run the
agent wrote `git diff -- ... > patch.txt`, changing the workspace and not one
line of source. Deciding after the fact which files are "real" would be choosing
the answer.

### Transition

    source_changed    = tracked_diff_hash   changed since the previous action
    workspace_changed = workspace_diff_hash changed since the previous action

A fact about the container, not a reading of the command. On the validation run
the correspondence was exact, with no exceptions:

| signature | n | state changed |
|---|---|---|
| `cat:heredoc,redirect` | 11 | 11 |
| `git:redirect` | 1 | 1 |
| `python` | 12 | 0 |
| `python:pytest` | 7 | 0 |
| `cat` | 3 | 0 |
| `sed` | 3 | 0 |

### Outcome

Final patch fingerprint, SWE-bench test result, `exit_status`. All deterministic;
no LLM judge.

## What `coding/1` deliberately excludes

- reasoning and thought text
- semantic labels such as search / inspect / edit
- hypothesis, commitment, or narrowing constructs
- recovery mode
- LLM-judged equivalence of any kind

This list is the point of the version number. If a later experiment is
disappointing, the temptation is to reach for reasoning text to rescue it. Adding
any of the above means `coding/2` and a written reason, not a quiet edit.

## Measurement, not intervention

The probe runs as a separate `docker exec` after each action. Its output is never
merged into the observation, never appended to the message list, and never
reaches the model: the agent's context is byte-identical to an uninstrumented
run, which was checked by searching the trajectory for the probe's own markers
(0 occurrences over 42 actions). A failed probe records an error and does not
fail the run.

This is unlike raising a step budget or editing a prompt, which change the agent
being measured.

## Known gaps

- The last action of a run triggers `Submitted` before its probe, so a run has
  one fewer snapshot than actions. Nothing changes after submission.
- A custom `environment_class` must carry its own `image`: upstream's
  `swebench.py` injects the image only for the literal names `docker` and
  `swerex_modal`. Multi-instance runs need a per-instance config overlay.
