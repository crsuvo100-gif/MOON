---
name: github-agent-sync
description: Build autonomous agent GitHub sync/push with safe PAT auth.
---

# github-agent-sync

Build/operate an AI agent that keeps a local project synchronized with a GitHub
repo and autonomously pulls tools from it. Covers BOTH auth options and the
non-obvious credential quirk that breaks git-push even when the API says you
have write access.

## When to use
- Wiring an agent to "always stay connected to GitHub" for auto-install/pull of
  task-related tools.
- Implementing a safe `github_sync` tool (sync = push local; fetch = pull a
  file/plugin from the repo on demand).
- Any agent task that must push commits without a human at the keyboard.

## Auth — support BOTH options (operator asked for "both")
1. **PAT (`auth="pat"`)** — read `GITHUB_TOKEN` from env or a param. Inject it
   into the remote URL (`https://x-access-token:<TOKEN>@github.com/owner/repo`)
   ONLY for the duration of the push; never persist it in `.git/config` or any
   committed file. Scrub it immediately after (`git remote set-url origin
   https://github.com/owner/repo`).
2. **GitHub CLI (`auth="gh"`)** — `gh auth login --with-token < token`. Falls
   back to this when `gh` is installed; PAT is the reliable path when `gh`
   can't be installed.

## THE GOTCHA (most important lesson)
A fine-grained PAT returned **`push: true` from the API** but `git push` still
failed with **`403 remote: Write access to repository not granted.`**

Root cause: the token's **Contents** permission was edited *after* the token
was created. The REST API reflects the new grant, but the **git-transport
credential layer keeps the old (read-only) grant**. Editing permissions alone
does NOT fix git-push.

**Fix:** on the PAT settings page, click **Regenerate** (after confirming
Repository access = the target repo and Contents = Read and write). The
regenerated token pushes immediately. Reproduction recipe in
`references/fine_grained_pat_403.md`.

API check that lies: `curl -H "Authorization: Bearer $TOKEN"
https://api.github.com/repos/owner/repo` returns `permissions.push: true` — do
NOT trust this as proof git-push will work. The real test is `git push` itself.

## Token hygiene (non-negotiable)
- Never print the token in logs, chat, or commit messages.
- Never commit it; keep it in `.env` (gitignored) or pass via env only.
- After any push using a token-in-URL, reset the remote to the token-less URL
  and confirm `grep -c x-access-token .git/config` == 0.
- Verify the token is absent from the whole repo + git history before declaring
  done (`git log --all -p | grep -c <token-substring>`).

## Safety rules to bake into the tool
- Non-force push always. Never `git push --force` unless explicitly authorized.
- Never rewrite history. Never delete files without permission.
- Pause (return a "PAUSED: auth required" report) instead of bypassing auth.
- Exclude secrets via `.gitignore` + an unstage-secrets pass (regex for
  api_key/secret/token/*.pem/etc.) before commit.

## Verification checklist
1. Repo reachable: `git ls-remote --heads origin` (public) or API call (private).
2. Permissions: API check (advisory only) + actual `git push` to a test branch
   or `master:main` (non-force) as the real proof.
3. If 403 "Write access not granted" → regenerate the fine-grained PAT.

## Pitfalls
- Editing a fine-grained PAT's Contents permission after creation does not
  enable git-push; you must Regenerate. (See references file.)
- `gh` may be uninstallable in a sandbox (no package-repo access) — keep PAT as
  the primary path.
- A 404 on the repo URL means it doesn't exist yet (not an auth problem) —
  pause and tell the operator to create it.
