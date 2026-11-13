# Mode H: performance

- **Code level:** use the stack's benchmark tool on the base and on the change, with repeats. Build the base in a separate worktree (`git worktree add <tmp dir> <base>`, removed afterwards); never stash, switch branches or check out files in the user's tree. For Go: `go test -bench=<Name> -benchmem -run='^$' -count=6 ./<pkg>/...`, compared with `benchstat` if it is installed. For Python: `pytest-benchmark` or `pyperf` if the project uses them. For JS: the project's own bench script. Report per-op time and allocations with the deltas.
- **Load:**
  - Use the load script from the profile (for example a k6 or Locust file) if there is one; otherwise propose a minimal k6 script and show it before running.
  - Run it only against a target the profile's `## Environments` marks safe, a local one, or one the user named in this request.
  - State the virtual users, duration and target first. Load on a shared environment needs an explicit yes, because it affects other people.
  - Report p50/p95/p99 latency, the error rate, the throughput and the thresholds.
- **Baselines:** compare with the previous `*-perf-<slug>.md` report in `~/.bogusz/reports/` when there is one. Never call a single run a regression or an improvement: noise needs repeated runs.
