# Bogusz

A Claude Code plugin that tests your project the way a senior QA engineer would. Bogusz reads the code first, plans the tests, runs the narrowest ones that answer the question, investigates failures and reports only what the evidence shows. It can turn a confirmed bug into a GitHub issue with repro steps, drive a UI with Playwright screenshots, run benchmarks, load tests and security scans, and analyze a past Claude Code session to show which tests actually ran.

Its helpers are the Błażej subagents: Explorer, Analyst, UI and Security.

Bogusz knows nothing about your project until you give it a **profile**: one Markdown file that says where the code lives, how each test layer runs, which environments are safe and which commands must never run.

## Install

```bash
claude plugin marketplace add adrianhaj/bogusz
claude plugin install bogusz@bogusz
```

## Set up your project

You have three ways to create the profile:

- **With Bogusz installed:** run `/bogusz setup` in your project. Błażej Explorer drafts the profile and Bogusz asks where to save it.
- **With any coding agent** (Claude Code, Codex, Cursor, Copilot, …): copy the prompt below into the agent, running from your project's root folder. If the project spans several repos, run it from the folder that contains them.
- **By hand:** copy [`skills/bogusz/references/profile-template.md`](skills/bogusz/references/profile-template.md).

### The setup prompt

```text
Create a Bogusz test profile for this project. Bogusz is a QA agent; the profile tells it how to test the project. Work read-only until I confirm.

1. Find the repos: the current folder if it is a git repo, otherwise each direct subfolder that contains .git.
2. In each repo, read only these files when present: Makefile, justfile, Taskfile.yml, package.json, go.mod, pyproject.toml, setup.cfg, tox.ini, noxfile.py, Cargo.toml, pom.xml, build.gradle*, .github/workflows/*.yml, .gitlab-ci.yml, playwright.config.*, docker-compose*.yml, CLAUDE.md, AGENTS.md, CONTRIBUTING.md, README*. You may list folders to find where unit, integration and E2E tests live. Don't run any other command.
3. Prefer the commands CI actually runs over the ones docs suggest. Give the narrowest form the tool supports (one package, one file, one test); a narrow form you didn't see written down is [guess].
4. Tag every line or table row [found: <file>:<line>] when you read it, or [guess] when you inferred it; tag each part of a row that mixes both. Roots lines are plain paths with no tag. Write "none" in any section where you found nothing.
5. Never copy a password, token or key. Write only the names of the environment variables that hold them.
6. Leave "## Environments" and "## Forbidden commands" as "TODO (human)". You may list candidates under them (a deploy target, a default URL), each tagged [found: …], as hints. Don't decide which environment is safe.
7. Fill exactly these sections, in this order:

# <Project> test profile
## Roots
One absolute folder per line, no tag: the repo this profile covers, or, for several repos, the folder that contains them.
## Repos and test commands
Table: repo | language | scoped test command | needs (Docker, services, setup) | source.
## UI, performance and security entry points
Table: kind (UI dev server, UI E2E, load, benchmarks, scanners) | command | source.
## Cross-repo / API consumers
Who builds against this project's schemas, protos, OpenAPI specs or shared libraries. "none" for a single self-contained repo.
## E2E
Path fragments where end-to-end tests live (one per line), their areas, and how to run one area.
## Environments
TODO (human)
## Forbidden commands
TODO (human)
## Issue tracker
Default: GitHub issues on the repo that owns the faulty code.
## Known flaky tests
None recorded yet.
## Regression-prone areas
None recorded yet.

8. Show me the draft and a short "Gaps" list (what you could not determine and where you looked). Then ask where to save it:
   - .bogusz/profile.md in the repo, to share with the team (single repo), or
   - ~/.bogusz/profiles/<project-name>.md, to keep it private or to cover several repos.
   Write the file only after I answer.
```

### Then fill in by hand

The agent can't know these, so the profile isn't finished until a person has filled them in:

- **Environments:** which targets Bogusz may test against (local, a named staging) and which are shared or production. Add the names of the credential variables, for example `TEST_USER` and `TEST_USER_PASSWORD`. Until this section is filled in, Bogusz runs no E2E or load tests and no deploy-like commands.
- **Forbidden commands:** deploy, destroy, migrate and reset targets, and CI workflows that touch shared systems.
- **Known flaky tests** and **regression-prone areas**, if you know any. Session analyses propose additions over time.
- Check each `[guess]` line, then remove its tag.

**Commit or keep private?** Commit `.bogusz/profile.md` when the whole team should share it and it names nothing sensitive. Keep it in `~/.bogusz/profiles/` when it names internal environments, or when it spans several repos.

### Example

A fictional shop with a Go API, a React UI and Postgres in Docker Compose:

```markdown
# acme-shop test profile

## Roots
~/src/acme-shop

## Repos and test commands
| Repo | Lang | Scoped test command | Needs | Source |
|---|---|---|---|---|
| api/ | Go | `go test ./internal/<pkg>/... -run <Test>` | Docker for `-tags integration` | .github/workflows/ci.yml:31 |
| web/ | TS | `npm test -- <file>` (Vitest) | — | web/package.json:9 |

## UI, performance and security entry points
| Kind | Command | Source |
|---|---|---|
| UI dev server | `cd web && npm run dev` → http://localhost:5173 | web/package.json:7 |
| UI E2E | `cd web && npx playwright test <spec>` | web/playwright.config.ts |
| Load | `k6 run load/checkout.js` | load/checkout.js |
| Scanners | `govulncheck ./...` (api), `npm audit --omit=dev` (web) | .github/workflows/scan.yml:12 |

## Cross-repo / API consumers
web/ calls the API through the generated client in web/src/api (from api/openapi.yaml).

## E2E
web/e2e
Areas: checkout, accounts. One area: `npx playwright test e2e/checkout`.

## Environments
- Local: `docker compose up -d db && go run ./cmd/api` — safe.
- staging.acme.test — safe for E2E; load tests need a yes.
- Production — never.
- Credentials: `E2E_USER`, `E2E_PASSWORD`.

## Forbidden commands
`make deploy`, `make db-reset`, the `release.yml` workflow.

## Issue tracker
GitHub issues on acme/shop, label `bug`.

## Known flaky tests
None recorded yet.

## Regression-prone areas
Checkout totals with discounts (api/internal/pricing).
```

## Use

```
/bogusz setup
/bogusz test the pricing package
/bogusz plan tests for https://github.com/<owner>/<repo>/pull/<n>
/bogusz investigate why web/src/cart.test.ts fails
/bogusz bug discount is applied twice for repeat customers   # reproduce, verdict, draft issue; files only on your yes
/bogusz ui log in and check out one item                     # Playwright screenshots in ~/.bogusz/ui/<slug>/
/bogusz perf checkout endpoint on local                      # benchmarks or k6, p50/p95/p99
/bogusz security authz on the orders API                     # scanners + negative authz tests
/bogusz explore edge cases for refunds
/bogusz regression-test
/bogusz report
/bogusz analyze-session last
```

## How it finds the profile

1. `.bogusz/profile.md` at the git toplevel of the current folder.
2. The file in `~/.bogusz/profiles/` whose `## Roots` covers the current folder.
3. If neither exists, it runs setup.

Bogusz prints which profile it used, checks every fact against the current code, and treats `TODO (human)` as unknown.

## What it reads and writes

- **Reads:** your code, and the profile. For `analyze-session`, it also reads Claude Code transcripts under `~/.claude/projects/`, read-only, and only those for sessions started inside the profile's roots.
- **Writes:** `~/.bogusz/digests/<session id>.json` (the redacted digest of an analyzed session, one file per analysis), `~/.bogusz/reports/*.md`, and Playwright files under `~/.bogusz/ui/`. All of these are outside your repos. Two things can land in a repo: the profile, saved or edited only after you say yes, and the negative tests a security run adds, which it leaves uncommitted.
- **Redaction** removes JWTs, bearer and vendor tokens, cloud keys, private keys, cookies, kubeconfig credentials, credentials in URLs and CLI flags, and secret-named keys and assignments. It is regex-based and **best effort**: review reports before you share them.
- **Network:** Bogusz has no hooks or background jobs of its own; its network use comes from the commands it runs for you. A UI check installs Playwright and Chromium from npm, a load test sends traffic to a target you approved, and `gh` searches and files issues, filing only after you approve. A dev server it starts for a UI check is stopped when the check is done.
- Claude Code deletes transcripts after `cleanupPeriodDays` (default 30).

## Safety

Bogusz never runs destructive commands against production, never deploys or migrates shared databases, and never runs anything under `## Forbidden commands` unless you ask. Before any external or persistent change it states the risk and waits for a yes. It never claims a pass without a run, and never hides a failure.

## Layout

| Path | What |
|---|---|
| `skills/bogusz/SKILL.md` | Bogusz: profile lookup, routing, modes, safety |
| `skills/bogusz/references/profile-template.md` | The profile sections |
| `skills/bogusz/references/reporting.md` | Report, session-analysis and bug-issue templates |
| `skills/bogusz/references/ui.md`, `perf.md`, `security.md` | Modes G, H and I, read only when a request routes there |
| `skills/bogusz/scripts/sessions.py`, `redact.py` | Transcript lookup and parsing, test detection, redaction (Python stdlib) |
| `agents/blazej-explorer.md` | Maps an area; discovers a project and drafts its profile |
| `agents/blazej-analyst.md` | Critiques a past session from its digest |
| `agents/blazej-ui.md` | Playwright flows with screenshots, console and network errors |
| `agents/blazej-security.md` | Read-only review that turns gaps into negative tests |

## Develop

```bash
python3 -m unittest discover -s tests -t .
claude plugin validate .
```

`tests/test_docs.py` checks that the setup prompt above lists every section of the profile template.

## License

Apache-2.0
