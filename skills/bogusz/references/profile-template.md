# <Project> test profile

A profile tells Bogusz how to test one project: where its code lives, how to run each test layer, and what must never be run. Every line is a fact with its source: `[found: file:line]` when it was read from the project, `[guess]` when it was inferred, or no tag once a person has checked it. A table row that mixes both tags each part. Write `none` in a section where nothing applies. Never write credential values here, only the names of the environment variables that hold them.

## Roots

One absolute folder per line, `~` allowed, and no tags: Bogusz passes these lines to session analysis as they are. These are the folders this profile covers; session analysis looks only at sessions started inside them.

## Repos and test commands

| Repo / folder | Language | Scoped test command | Needs (Docker, services, setup) | Source |
|---|---|---|---|---|
| `.` | Go | `go test ./internal/<pkg>/... -run <Test>` | Docker for `integration/` | `[found: Makefile:12]` |

Prefer the commands CI runs. Include the narrowest form (one package, one file, one test) when the tool supports it.

## UI, performance and security entry points

| Kind | Entry point | Source |
|---|---|---|
| UI dev server | `npm run dev` → `http://localhost:5173` | |
| UI E2E | `npx playwright test <spec>` | |
| Load | `k6 run load/smoke.js` | |
| Scanners | `govulncheck ./...`, `npm audit --omit=dev` | |

## Cross-repo / API consumers

Who builds against this project's APIs, schemas or shared libraries, so a change here can break them. Write "none" for a single self-contained repo.

## E2E

Where end-to-end tests live (one path fragment per line; session analysis marks runs there as E2E), their areas, and how to run one area.

## Environments

TODO (human). Which targets are safe to test against (local, a named staging), which are shared or production and need an explicit yes, and the names of the credential environment variables. Until this is filled in, Bogusz runs no E2E, load or deploy-like command.

## Forbidden commands

TODO (human). Deploy, destroy, migrate or reset targets and workflows Bogusz must never run without being asked, e.g. `make deploy`, `terraform apply`, `*-destroy`.

## Issue tracker

Where bugs are filed. Default: GitHub issues on the repo that owns the faulty code (`git remote get-url origin`). Add labels or templates the project uses.

## Known flaky tests

None recorded yet.

## Regression-prone areas

None recorded yet.
