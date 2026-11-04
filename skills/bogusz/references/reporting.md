# Bogusz report templates

Tag every result line `[ran: <command>]` or `[not run]`. Label anything that is not direct evidence `[interpretation]` or `[assumption]`. Commands are written exactly as run, minus secrets.

## Test report

```markdown
# Test report: <subject>  (<YYYY-MM-DD>, repo@branch <sha>)

## What was tested
## Why
<requirement / risk each test covers>
## Environment
<repo, branch, Go/Python version, Docker yes/no, E2E env URL or "none">
## Commands
<one per line, in order>
## Results
| Test / scope | Status | Evidence |
|---|---|---|
<passed / failed / skipped / not run, with counts from the runner summary>
## Bugs found
## Known limitations
<what could not be tested and why>
## Regression risks
## Quality assessment
<the table below>
## Recommendations
```

### Extra sections for UI, performance and security runs

Add whichever applies under `## Results`:

```markdown
### UI (<base URL>, <viewport>)
| # | Step | Expected | Result | Screenshot |
Console errors / failed requests: <list or "none">

### Performance
| Metric | Base | Change | Δ | Runs |
<ns/op, B/op, allocs/op from -count=6, or k6 p50/p95/p99, error rate, RPS>
Load: <tool, VUs, duration, target>. Noise note: <spread across runs>

### Security
| Tool / check | Findings (crit/high/med/low) | Notable | Evidence |
| Gap (from review) | Test that proves it | Status (confirmed / not reproduced / not tested) |
```

## Session analysis report

```markdown
# Session analysis: <session-id>  (<started_at>, <cwd>@<git_branch>)

1. Session overview: duration, tool calls, subagents, interrupted y/n, malformed lines
2. Original objective: from the first prompt, quoted (seq N)
3. Testing approach: what was read before testing, which layers were chosen
4. Chronological activity: seq-ordered, one line each, test runs in bold
5. Tests actually executed: table of command | runner | layer | attempt | status | counts | seq
   plus "Discussed, not run" and "Blocked by hook"
6. Results and failures: each failure, what happened next, whether it was resolved
7. Testing quality assessment: the table below
8. Missed test scenarios
9. Lessons learned
10. Recommendations for future sessions

Proposed profile updates: a diff against the project's profile
```

## Bug report (GitHub issue body)

Title: `<component>: <actual behaviour> when <trigger>`. Keep it under 80 characters, and name the symptom, not the suspected fix.

```markdown
## Summary
<one or two sentences: what breaks, for whom, how badly>

## Environment
- Component / repo: <repo> @ <commit or version>
- Runtime: <local / kind / env name>, Go/Python version, client version
- Verdict: confirmed — reproduced <N>/<N> runs on <date>

## Steps to reproduce
1. <exact command or call>
2. …

<minimal repro: failing test, script or curl/grpcurl call, copy-pasteable>

## Expected
<behaviour, citing docs/proto/tests when they define it>

## Actual
<exact error / output, redacted, trimmed to the relevant lines>

## Evidence
- [ran: <command>] → <result>
- Code: `<file:line>` <why it is the likely cause>  [interpretation]

## Impact and scope
<who hits it, workaround if any, related components (from the profile)>

## Suggested fix / test
<optional; the regression test that should guard it>
```

Every line in Evidence is either `[ran: …]` or labelled `[interpretation]`. A `not reproduced` result never becomes an issue; report it to the user with what was tried.

## Quality assessment (both reports)

Rate each row `covered`, `partial`, `missing` or `n/a`, with one line of evidence (seq numbers or commands). No numeric scores.

| Criterion | Asks |
|---|---|
| Requirement coverage | Is every acceptance criterion exercised by a run test? |
| Risk coverage | Were the profile's regression-prone areas the change touches tested? |
| Boundary and negative cases | Invalid input, empty, limits, unauthorised, not-found? |
| Assertion quality | Do the assertions check behaviour, not just "no error"? Was any assertion weakened? |
| Reliability | Deterministic? Any flaky suspects (same command, different result, no edit)? |
| Execution efficiency | Narrow scope first? Repeated identical failing runs? |
| Evidence quality | Does every conclusion rest on `passed`/`failed` runs, not `unknown`/`blocked`/none? |
| Regression protection | Is there now a test that would catch this bug or behaviour again? |
