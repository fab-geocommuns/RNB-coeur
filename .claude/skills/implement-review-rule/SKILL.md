---
name: implement-review-rule
description: Implement the static check a `PR review loop` issue asks for, as a rule that goes red on the commits reviewers commented on and runs in the existing pre-commit and CI suite. Use when asked to implement, handle or close a PR review loop issue, or to turn a recurring review comment into a lint rule or check.
---

# Implement a review rule

A `PR review loop` issue describes a **family**: one mistake that reviewers flagged in several PRs (see `docs/review-rules/LOOP.md`). Your job is the check that catches it from now on. The check earns its place by two observations: it goes **red** on the very code the reviewers commented on, and it stays **green** on the branch you ship, inside the suite the team already runs.

## Steps

### 1. Load the family

1. Read the issue with `gh api repos/fab-geocommuns/RNB-coeur/issues/<n>` (REST: GraphQL is blocked in Claude Code cloud sessions). Its first line holds the marker `<!-- pr-review-loop family=<id> -->`.
2. Read the family in the catalog: `git fetch origin claude/review-catalog`, then `git show origin/claude/review-catalog:docs/review-rules/catalog.yml`. Each occurrence gives `comment_id`, `pr`, `commit` and `path`.
3. For each occurrence, get the commented lines: `gh api repos/fab-geocommuns/RNB-coeur/pulls/comments/<comment_id> --jq '{original_start_line, original_line, diff_hunk, body}'`.

Done when every occurrence has its commit, path, commented line range and the reviewer's words.

### 2. Choose the check

Pick the first home that can express the check, in this order:

1. **A rule of a tool already in the suite** ([the suite](#the-suite)): a mypy setting, a bandit test, a hook option.
2. **A new pre-commit hook**: semgrep for project-specific code patterns, ruff for a known Python rule code, codespell for spelling. pre-commit.ci runs every hook on each PR, so a hook is in CI the moment it is in `.pre-commit-config.yaml`.
3. **A Django test**, when deciding needs the application running (API behaviour, documented responses, database state). The `tests.yml` workflow runs it.
4. **A step in a workflow**, for a check that needs the CI environment and fits none of the above.

Then mark each occurrence **catchable** (the check, as designed, would flag the commented code) or not, with a one-line reason. When fewer than 2 occurrences in 2 distinct PRs are catchable, the family fails the family test: post the analysis as a comment on the issue and stop.

Done when the check's home is chosen and every occurrence is marked.

### 3. Write the check and its fixtures

Write the check with the narrowest scope that still catches every catchable occurrence (paths, file types, patterns). It fails the run: a warning that lets the PR through catches nothing.

Write its fixtures from the real occurrences: a minimal **red** snippet per distinct shape of the mistake, copied from the commented code, and a **green** snippet showing the accepted way (for `building-direct-write`, a call to `Building.update()`). Where fixtures live depends on the tool ([tool notes](#tool-notes)).

Done when the fixtures run: red snippets flagged, green snippets clean.

### 4. Go red on the original commits

For every catchable occurrence:

```bash
git fetch origin <commit>
git worktree add --detach <scratchpad>/bt-<first 8 chars of commit> <commit>
```

Run the new check, from your branch, against the file of that worktree, the same way the suite runs it (for a semgrep rule: `semgrep --metrics=off --disable-version-check --config <your rule> <worktree>/<path>`). For a Django test, copy your test file into the worktree and run it there with its own compose project (`docker compose -p rnb-backtest -f docker-compose.test.yml up -d --build`, then `down -v` afterwards).

The occurrence is red when the check reports a finding in `<path>` on the commented lines (`original_start_line` to `original_line`, or `original_line` alone when the start is null), or at least within the `diff_hunk` the reviewer saw; for a test, when it fails on the behaviour the comment describes. Remove each worktree after use.

Done when every catchable occurrence is red. An occurrence that stays green means the check misses the mistake as it was really written: fix the check and run this step again.

### 5. Go green on your branch

Run the check over the whole repository at your branch head and handle every finding, one of three ways:

- **fix the code** in this PR, when the fix is mechanical and safe;
- **suppress inline with a reason** (`# nosemgrep: <rule-id>  <why this case is legitimate>`, `# noqa: <code>  <why>`), for a legitimate case such as a data fix;
- **narrow the scope** of the check, when a whole area legitimately differs (for example tests), and write that choice in the PR.

Run the rest of the suite too (`pre-commit run --all-files`, and the Django tests the change touches): the new check slots in beside the existing ones.

Done when the check reports zero findings on your branch and the suite is green.

### 6. Ship through CI

Open a PR whose body holds:
- `Closes #<issue>`: merging closes the issue as completed, which marks the family shipped in the catalog;
- the backtest table: occurrence (PR, comment link), commit, `path:line`, finding;
- the occurrences you marked not catchable, with their reason;
- how you handled each finding of step 5.

Read the PR's checks with `gh api repos/fab-geocommuns/RNB-coeur/commits/<head sha>/check-runs --jq '.check_runs[] | {name, conclusion}'`.

Done when the PR's checks show the new check ran and passed.

## Reference

### The suite

| Where | What runs | Add a check by |
|---|---|---|
| `.pre-commit-config.yaml`, run locally and by pre-commit.ci on every PR | trailing-whitespace, end-of-file-fixer, autoflake, isort, black | adding a hook |
| `.github/workflows/tests.yml` | `mypy .`, `makemigrations --check`, Django tests with coverage | a mypy setting in `app/pyproject.toml`, a test, or a step |
| `.github/workflows/sast.yml` | bandit on `app/` | a bandit setting in `app/pyproject.toml` |

pre-commit.ci installs hook environments itself: use hooks from a hook repository, or `language: python` with `additional_dependencies`. A hook with `language: system` or `docker` cannot run there.

### Tool notes

- **semgrep**: all project rules live in `.semgrep/`, one `<rule-id>.yaml` per rule with its fixtures beside it in `<rule-id>.py`, annotated `# ruleid: <rule-id>` above red lines and `# ok: <rule-id>` above green ones; `semgrep --test .semgrep/` runs them. One single pre-commit hook runs every rule of the folder: the first semgrep rule adds it (`--config .semgrep/ --error --metrics=off --disable-version-check`, fixtures excluded from the scan), later rules only add files.
- **ruff**: it is not in the suite yet. The first ruff rule adds the `ruff` hook (lint only, no formatter: black formats) with `[tool.ruff.lint] select` in `app/pyproject.toml` holding exactly the selected codes; later rules extend `select`. Its fixtures are the step 4 backtest itself.
- **codespell**: one hook; project words it must accept go in its `ignore-words-list`.
- **Django test**: place it beside the tests of the area it guards, under the existing `tests/` folders.
