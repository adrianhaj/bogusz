<!-- A real report, saved by Bogusz 0.4.0 in ~/.bogusz/reports/. The only edit: the path of the clone is written as <clone>. The appendix is not part of the saved report. -->

# Test report: UUID parsing in google/uuid (Parse, ParseBytes, Validate)  (2026-11-16, google/uuid@master 2d3c2a9)

## Verdict
Passed. 6 commands ran 58 tests and subtests with 0 failures, and two 10-second fuzz runs (6.5 million executions) found no panic. No bug found.
The biggest thing left untested: the callers that inherit Parse's leniency (`UnmarshalText`, `Scan`, JSON), and `MustParse`.

## What was tested
The three functions that turn text into a UUID: `Parse` (uuid.go:95), `ParseBytes` (uuid.go:148) and `Validate` (uuid.go:223). They are three hand-copied versions of the same logic, so the plan checks each rule on all three and checks that they agree.

profile: `.bogusz/profile.md` in the clone (drafted in this run; `## Environments` and `## Forbidden commands` are `TODO (human)`).

## Environment
- Repo: a fresh clone of github.com/google/uuid, branch master, commit 2d3c2a9.
- Go 1.27.3 darwin/arm64. CI tests Go 1.19, 1.20.x and 1.21 (.github/workflows/tests.yaml:13), so this run used a newer Go than CI does.
- Docker: not needed. E2E environment: none.

## Commands
Every command ran from the clone's root (`cd <clone> && …`).

1. `go test -count=1 -v -run '^(TestUUID|TestCoding|TestWrongLength|TestIsWrongLength|TestValidate)$' .` (blocked, see `## Blocked`)
2. `go test -count=1 -v -run '^TestUUID$' .`
3. `go test -count=1 -v -run '^TestCoding$' .`
4. `go test -count=1 -v -run '^TestValidate$' .`
5. `go test -count=1 -v -run '^TestParse' .`
6. `go test -count=1 -run '^$' -fuzz '^FuzzParse$' -fuzztime 10s .`
7. `go test -count=1 -v -run '^TestWrongLength$' .`
8. `go test -count=1 -run '^$' -fuzz '^FuzzParseBytes$' -fuzztime 10s .`
9. `go test -count=1 -v -run '^TestIsWrongLength$' .`

## Results
| ID | Requirement / risk | Case | Layer | Status | Evidence |
|---|---|---|---|---|---|
| T1 | The canonical form decodes to the right 16 bytes | `00112233-4455-6677-8899-aabbccddeeff` → `00 11 22 … ff` | unit | passed | `[ran: go test -count=1 -v -run '^TestCoding$' .]` 1 passed (existing); `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParseDecodesAllForms/canonical` passed (new) |
| T2 | The URN, braced and raw-hex forms decode to the same bytes | `urn:uuid:…`, `{…}`, 32 hex digits → the same 16 bytes | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParseDecodesAllForms` urn, braces, raw_hex passed (new) |
| T3 | Hex digits and the URN prefix are case-insensitive | upper-case and mixed-case input of each form → the same 16 bytes | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` 5 upper and mixed subtests passed (new); `[ran: go test -count=1 -v -run '^TestUUID$' .]` 1 passed (existing) |
| T4 | A wrong length returns `ErrInvalidLength` | 0, 31, 33, 35, 37, 39, 44 and 46 bytes | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParseRejectsWrongLength` 8 subtests passed (new); `[ran: go test -count=1 -v -run '^TestWrongLength$' .]` 1 passed and `[ran: go test -count=1 -v -run '^TestIsWrongLength$' .]` 1 passed (existing) |
| T5 | A misplaced hyphen or a non-hex byte returns `ErrInvalidUUIDFormat` | each of the 4 hyphens replaced; a hyphen in a hex position; `g` first and last; trailing newline; a 2-byte `é`; in the canonical and raw-hex forms | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParseRejectsBadFormat` 11 subtests passed (new) |
| T6 | A 45-byte input with another prefix returns `ErrInvalidURNPrefix` | `urn:test:…`, `urn-uuid:…`, `123456789…` | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParseRejectsBadURNPrefix` 3 subtests passed (new) |
| T7 | 38-byte input: `Parse` reads only the middle 36 bytes (documented), `Validate` requires braces | `[…]`, `x…y`, `{…x`, `x…}` → `Parse` and `ParseBytes` return the UUID; `Validate` returns `ErrInvalidBracketedFormat` | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParse38ByteDelimiters` 4 subtests passed (new) |
| T8 | `ParseBytes` behaves as `Parse` | every input of T1–T7 → the same value and the same error class | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` asserted in all 39 subtests (new) |
| T9 | `Validate` agrees with `Parse`, except for T7 | every input of T1–T6 → nil when `Parse` succeeds, the same error class when it fails | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` asserted in 35 subtests (new); `[ran: go test -count=1 -v -run '^TestValidate$' .]` 10 passed (existing) |
| T10 | `Validate` rejects bad content inside a URN or braces | `urn:uuid:g…`, `{g…}`, and each with a hyphen replaced | unit | passed | `[ran: go test -count=1 -v -run '^TestParse' .]` `TestParseRejectsBadFormat` 4 urn and braces subtests passed (new) |
| T11 | No input makes the parser panic | the repo's `FuzzParse` and `FuzzParseBytes`, 10 s each | fuzz | passed | `[ran: go test -count=1 -run '^$' -fuzz '^FuzzParse$' -fuzztime 10s .]` `execs: 3372686`, `PASS`; `[ran: go test -count=1 -run '^$' -fuzz '^FuzzParseBytes$' -fuzztime 10s .]` `execs: 3131431`, `PASS` |
| T12 | The callers of the parser reject what it rejects | `UnmarshalText` (marshal.go:18), `NullUUID.UnmarshalText` (null.go:90), `Scan` (sql.go:27) with the T4–T7 inputs | unit | not run | `[not run]` outside the request (Parse, ParseBytes, Validate) |
| T13 | `MustParse` panics on bad input | `MustParse("x")` → panic with the input in the message | unit | not run | `[not run]` outside the request |

Counts come from `sessions.py tests`: TestUUID 1, TestCoding 1, TestValidate 10, TestParse 44, TestWrongLength 1, TestIsWrongLength 1 (read from the `-v` output; that run came after the listing). Go counts a parent test and each subtest, so the 44 are 5 test functions and 39 subtests.

## Blocked
- `go test -count=1 -v -run '^(TestUUID|TestCoding|TestWrongLength|TestIsWrongLength|TestValidate)$' .`
  Refusal: `PreToolUse:Bash hook error: [~/.claude/hooks/bash-guard.sh]: Blocked: run lint/tests unpiped (no | or || true) so the exit code is visible; check it before pushing.`
  The hook read the `|` in the `-run` pattern as a shell pipe. The command never ran. The five tests it names ran one per command (commands 2, 3, 4, 7 and 9), which is the form the hook asks for. To run them in one command, allow a quoted `|` in the hook.

## Bugs found
None.

## Files added or changed
- `parse_test.go`: new, 5 test functions, 39 cases. Uncommitted on master of the clone.
- `.bogusz/profile.md`: new, the drafted profile. Uncommitted on master of the clone.

## Known limitations
- The session started outside the profile's root, so `sessions.py tests` found it only with `--root` set to the folder the session started in.
- Fuzzing ran 10 s per target. The repo's fuzz targets assert nothing; they fail only on a panic.
- Run on Go 1.27.3 only, not on the Go versions of the CI matrix.
- The new tests live in package `uuid`, as the repo's tests do, but call only exported functions.

## Regression risks
- `Parse`, `ParseBytes` and `Validate` hold three copies of the same offsets and length rules. Before this run, no test compared `Validate` with `Parse`, and `ParseBytes` was compared with `Parse` by value on valid input only (uuid_test.go:123). `[interpretation]` A fix applied to one copy could go unnoticed in the others.
- `UnmarshalText`, `NullUUID.UnmarshalText` and `Scan` call the parser directly (marshal.go:18, null.go:90, sql.go:27), so they accept a 38-byte value with any byte at each end, as T7 shows for `Parse`. `[interpretation]` from reading the code; not run.

## Quality assessment
| Criterion | Rating | Evidence |
|---|---|---|
| Requirement coverage | covered | T1–T11 each have a passing run; every form in the doc comment of `Parse` (uuid.go:86-94) is decoded and compared with literal bytes |
| Risk coverage | n/a | the profile's `## Regression-prone areas` is empty |
| Boundary and negative cases | covered | lengths on both sides of 32, 36, 38 and 45 (T4), every hyphen position, first and last byte, non-ASCII (T5) |
| Assertion quality | partial | New tests compare with a literal and with the exported error values. The existing `TestUUID` checks only `err == nil` and the version and variant nibbles (uuid_test.go:98-113), so a wrong byte elsewhere would pass. Its messages end in `\b`, probably meant as `\n` (uuid_test.go:101, 108, 111, 118, 125) `[interpretation]` |
| Reliability | covered | the tests that ran use fixed inputs, with no clock or randomness; each ran once with `-count=1` |
| Execution efficiency | covered | one test per command, never `./...`; one blocked command, not retried in the same form |
| Evidence quality | covered | every passed row rests on a `passed` run; the two fuzz runs are quoted from their `PASS` and `execs` lines |
| Regression protection | covered | `parse_test.go` now fails if the three functions stop agreeing or a form decodes to other bytes; it is uncommitted |

## Recommendations
1. Offer `parse_test.go` upstream, or keep its cases in a local fork: it is the only test that compares the three functions.
2. Give the fuzz targets a property to check, for example `Validate(s) == nil` implies `Parse(s)` succeeds, and `Parse(s)` equals `ParseBytes([]byte(s))`.
3. Add T12: the same rejected inputs through `UnmarshalText` and `Scan`.
4. Callers who need strict input should call `Validate` first: `Parse` accepts `[…]` and `x…y`, as its doc comment says.

## Appendix: the test file Bogusz added

`parse_test.go`, as it was when the commands above ran:

```go
package uuid

import (
	"errors"
	"testing"
)

const (
	canonical = "00112233-4455-6677-8899-aabbccddeeff"
	rawHex    = "00112233445566778899aabbccddeeff"
)

var canonicalBytes = UUID{
	0x00, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77,
	0x88, 0x99, 0xaa, 0xbb, 0xcc, 0xdd, 0xee, 0xff,
}

type parseCase struct {
	name string
	in   string
}

func checkValue(t *testing.T, fn, in string, got UUID, err, wantErr error) {
	t.Helper()
	if !errors.Is(err, wantErr) {
		t.Errorf("%s(%q) error = %v, want %v", fn, in, err, wantErr)
		return
	}
	if wantErr == nil && got != canonicalBytes {
		t.Errorf("%s(%q) = %x, want %x", fn, in, got[:], canonicalBytes[:])
	}
}

// Parse, ParseBytes and Validate must agree: same value, same error class.
func checkAll(t *testing.T, cases []parseCase, wantErr error) {
	t.Helper()
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, err := Parse(c.in)
			checkValue(t, "Parse", c.in, got, err, wantErr)
			got, err = ParseBytes([]byte(c.in))
			checkValue(t, "ParseBytes", c.in, got, err, wantErr)
			if err := Validate(c.in); !errors.Is(err, wantErr) {
				t.Errorf("Validate(%q) = %v, want %v", c.in, err, wantErr)
			}
		})
	}
}

func TestParseDecodesAllForms(t *testing.T) {
	checkAll(t, []parseCase{
		{"canonical", canonical},
		{"urn", "urn:uuid:" + canonical},
		{"braces", "{" + canonical + "}"},
		{"raw hex", rawHex},
		{"canonical upper", "00112233-4455-6677-8899-AABBCCDDEEFF"},
		{"canonical mixed", "00112233-4455-6677-8899-aAbBcCdDeEfF"},
		{"urn upper", "URN:UUID:00112233-4455-6677-8899-AABBCCDDEEFF"},
		{"braces upper", "{00112233-4455-6677-8899-AABBCCDDEEFF}"},
		{"raw hex upper", "00112233445566778899AABBCCDDEEFF"},
	}, nil)
}

func TestParseRejectsWrongLength(t *testing.T) {
	checkAll(t, []parseCase{
		{"empty", ""},
		{"31", rawHex[:31]},
		{"33", rawHex + "0"},
		{"35", canonical[:35]},
		{"37", canonical + "0"},
		{"39", "{" + canonical + "}}"},
		{"44", "urn:uuid:" + canonical[:35]},
		{"46", "urn:uuid:" + canonical + "0"},
	}, ErrInvalidLength)
}

func TestParseRejectsBadFormat(t *testing.T) {
	checkAll(t, []parseCase{
		{"no hyphen at 8", canonical[:8] + "0" + canonical[9:]},
		{"no hyphen at 13", canonical[:13] + "0" + canonical[14:]},
		{"no hyphen at 18", canonical[:18] + "0" + canonical[19:]},
		{"no hyphen at 23", canonical[:23] + "0" + canonical[24:]},
		{"hyphen in a hex position", "-" + canonical[1:]},
		{"non-hex first", "g" + canonical[1:]},
		{"non-hex last", canonical[:35] + "g"},
		{"trailing newline", canonical[:35] + "\n"},
		{"non-ASCII", canonical[:34] + "é"},
		{"raw hex, non-hex first", "g" + rawHex[1:]},
		{"raw hex, non-hex last", rawHex[:31] + "g"},
		{"urn, non-hex", "urn:uuid:g" + canonical[1:]},
		{"urn, no hyphen at 8", "urn:uuid:" + canonical[:8] + "0" + canonical[9:]},
		{"braces, non-hex", "{g" + canonical[1:] + "}"},
		{"braces, no hyphen at 8", "{" + canonical[:8] + "0" + canonical[9:] + "}"},
	}, ErrInvalidUUIDFormat)
}

func TestParseRejectsBadURNPrefix(t *testing.T) {
	checkAll(t, []parseCase{
		{"other namespace", "urn:test:" + canonical},
		{"wrong separator", "urn-uuid:" + canonical},
		{"nine other bytes", "123456789" + canonical},
	}, ErrInvalidURNPrefix)
}

// Documented at Parse: "Only the middle 36 bytes are examined" for 38-byte input.
func TestParse38ByteDelimiters(t *testing.T) {
	for _, in := range []string{
		"[" + canonical + "]",
		"x" + canonical + "y",
		"{" + canonical + "x",
		"x" + canonical + "}",
	} {
		t.Run(in, func(t *testing.T) {
			got, err := Parse(in)
			checkValue(t, "Parse", in, got, err, nil)
			got, err = ParseBytes([]byte(in))
			checkValue(t, "ParseBytes", in, got, err, nil)
			if err := Validate(in); !errors.Is(err, ErrInvalidBracketedFormat) {
				t.Errorf("Validate(%q) = %v, want %v", in, err, ErrInvalidBracketedFormat)
			}
		})
	}
}
```
