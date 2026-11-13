# Bogusz report templates

Tag every result line `[ran: <command>]` or `[not run]`. Label anything that is not direct evidence `[interpretation]` or `[assumption]`. Commands are written exactly as run, minus secrets.

## Test plan

Mode B writes this table. The report's results table reuses its rows and IDs.

```markdown
| ID | Requirement / risk | Case (input → expected) | Layer | Why |
|---|---|---|---|---|
| T1 | <acceptance criterion or regression risk> | <one case> | <unit / integration / API / E2E> | <what would go unnoticed without it> |
```

## Test report

```markdown
# Test report: <subject>  (<YYYY-MM-DD>, repo@branch <sha>)

## Verdict
<two lines at most: passed / failed / inconclusive, the counts, the bugs found, the biggest thing left untested>
## What was tested
## Environment
<repo, branch, Go/Python version, Docker yes/no, E2E env URL or "none">
## Commands
<one per line, in order>
## Results
| ID | Requirement / risk | Case | Layer | Status | Evidence |
|---|---|---|---|---|---|
<every row of the plan. Status: passed / failed / skipped / blocked / not run. Evidence: `[ran: <command>]` with the counts from the runner summary, or `[not run]` with the reason>
## Blocked
<each refused command, the refusal text, and what the user can run or approve to unblock it; "none" otherwise>
## Bugs found
## Files added or changed
<each test or file Bogusz added or edited, and where it is: "uncommitted on <branch>" or the commit; "none" otherwise>
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
Traces of failed steps: <path to each trace.zip, or "none">
<a before/after run uses: | # | Step | Before | After | Differs? | Screenshots |>

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
   plus "Discussed, not run" and "Blocked (hook or permission prompt)"
6. Results and failures: each failure, what happened next, whether it was resolved
7. Testing quality assessment: the table below
8. Missed test scenarios
9. Lessons learned
10. Recommendations for future sessions

Proposed profile updates: a diff against the project's profile
```

The analyst fills sections 1–10. When Bogusz saves the report, it adds this above section 1:

```markdown
## Verdict
<what ran, what the evidence supports, what was lost or left unverified>
```

## Bug report (GitHub issue body)

Title: `<component>: <actual behaviour> when <trigger>`. Keep it under 80 characters, and name the symptom, not the suspected fix. The title is passed to `gh issue create --title`. The saved draft starts at `## Summary`, because the whole file becomes the issue body.

```markdown
## Summary
<one or two sentences: what breaks, for whom, how badly>

## Environment
- Component / repo: <repo> @ <commit or version>
- Runtime: <local / kind / env name>, Go/Python version, client version
- Verdict: confirmed — reproduced <red>/<runs> runs on <date>
- Introduced by: <PR or commit, when `git log` or `git blame` shows it; leave this line out otherwise>

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
| Assertion quality | Do the assertions check behaviour, not just "no error"? Was any assertion weakened? Any expected value computed the way the code computes it, or a check that goes around the public interface (mocked internal collaborators, reading storage directly)? |
| Reliability | Deterministic? Any flaky suspects (same command, different result, no edit)? |
| Execution efficiency | Narrow scope first? Repeated identical failing runs? |
| Evidence quality | Does every conclusion rest on `passed`/`failed` runs, not `unknown`/`no_tests`/`blocked`/none? |
| Regression protection | Is there now a test that would catch this bug or behaviour again? |
