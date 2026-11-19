---
name: pr-risk
description: Classify a pull request of this repository by risk and apply its risk label on GitHub. Use right after opening a PR, after a push to a branch with an open PR, or when asked to (re)classify a PR's risk.
---

# PR risk labelling

A subagent classifies the PR, so the verdict comes from a reader that only sees the diff and the rules, not the story of the session that wrote the PR. This session only applies the verdict. Risk labels so far: `risque bas`.

## Steps

1. Dispatch one subagent with the Agent tool (`subagent_type: general-purpose`, `model: sonnet`) and this prompt, `<number>` filled in:

   > Classify pull request #<number> of the git repository at <absolute path of this repository's root>. Read `.claude/skills/pr-risk/classify.md` in that repository and follow it exactly. Stay read-only. Reply with the report the file describes, nothing else.

   Done when its report arrives and its first line is `LEVEL: risque bas` or `LEVEL: none`. Any other first line: report the problem to the user and stop, leaving the labels as they are.

2. Read the PR's current labels:

   ```bash
   gh pr view <number> --json labels --jq '.labels[].name'
   ```

3. Bring the labels in line with the verdict: verdict `risque bas` and label absent → `gh pr edit <number> --add-label "risque bas"`; verdict `none` and label present → `gh pr edit <number> --remove-label "risque bas"`. Otherwise the labels already match. If GitHub answers that the label does not exist, stop and tell the user; leave label creation to them.

4. Report to the user: the verdict, what changed on the PR (label added, removed, or unchanged), and the subagent's per-file lines.
