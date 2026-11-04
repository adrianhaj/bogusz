"""Secret redaction for anything Bogusz prints or stores from a transcript."""

import re
from pathlib import Path

_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)"), None),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), None),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"), None),
    ("github", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), None),
    ("aws", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), None),
    ("vendor", re.compile(
        r"\b(?:sk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}"
        r"|glpat-[0-9A-Za-z_-]{20,}|hf_[A-Za-z0-9]{30,}|[sr]k_live_[0-9A-Za-z]{16,}|npm_[A-Za-z0-9]{36}"
        r"|ya29\.[0-9A-Za-z_-]{20,})"
    ), None),
    ("webhook", re.compile(r"(\bhooks\.slack\.com/services/)[A-Za-z0-9/]+"), 1),
    ("query", re.compile(r"(?i)([?&](?:sig|signature|x-amz-signature|x-amz-credential|x-goog-signature)=)[^&\s\"'#]+"), 1),
    ("arn", re.compile(r"\barn:aws[\w-]*:[^\s\"',]+"), None),
    ("mc", re.compile(r"(\bmc\s+alias\s+set\s+\S+\s+\S+\s+)[^\s'\"&;|]+\s+[^\s'\"&;|]+"), 1),
    ("cookie", re.compile(r"(?im)^(\s*(?:set-)?cookie:\s*).+$"), 1),
    ("kube", re.compile(r"(?i)\b((?:client-key|client-certificate|certificate-authority)-data\s*:\s*)\S+"), 1),
    ("url", re.compile(r"((?<![a-z0-9+.-])[a-z][a-z0-9+.-]{0,30}://[^/\s:@]{0,256}:)[^\s/]+@"), 1),
    # Key patterns anchor on the keyword and cap repeats at 64: an unbounded `[\w-]*` before a keyword is O(n²) on long
    # lines, and anchoring on where the key starts misses long or prefixed keys.
    ("header", re.compile(
        r"(?im)((?:authorization|(?:-H|--header)\s*=?\s*\\?[\"']?[A-Za-z0-9-]{0,64}(?:token|key)"
        r"|[A-Za-z0-9]{1,32}-[A-Za-z0-9-]{0,64}(?:token|key))\s*:\s*)(?=[^\s\"'])[^\r\n\"'\\]+"
    ), 1),
    ("flag", re.compile(r"(?i)((?<![\w-])--?[\w-]{0,64}(?:password|passwd|secret|token|api-?key)[\w-]{0,64}[ =])[^\s\"']+"), 1),
    # After curl/wget/http (across `\` line continuations) any -u value is a credential; elsewhere only `user:pass`
    # shapes are, so a bare `git push -u origin` stays.
    ("flag", re.compile(r"(\b(?:curl|wget|http)\b(?:[^\n]|\\\n){0,400}?\s(?:-u|--user)[ =])\S+"), 1),
    ("flag", re.compile(r"(\s(?:-u|--user)[ =])[^\s:]*:\S*"), 1),
    ("flag", re.compile(r"(\blogin\b[^\n]*?\s-p\s+)\S+"), 1),
    ("flag", re.compile(r"(\bmysql\b[^\n]*?\s-p)[^\s]+"), 1),
    ("flag", re.compile(r"(\bsshpass\b[^\n]*?\s-p\s*)\S+"), 1),
    ("flag", re.compile(r"(\bredis-cli\b[^\n]*?\s-a\s+)\S+"), 1),
    ("netrc", re.compile(r"(?i)(\blogin\s+\S+\s+password\s+)\S+"), 1),
    # ponytail: also hits max_tokens=…; over-redaction is the safe side
    # A quoted value runs to the first quote followed by a delimiter, so escaped quotes and backslashes inside it stay covered.
    ("kv", re.compile(
        r"(?i)((?:secret|password|passwd|_pass\b|(?<=[\"'])auth(?=\\?[\"']\s*:)|token|api[_-]?key|access[_-]?key|"
        r"private[_-]?key|account[_-]?key|(?:master|encryption|signing|session|license|storage|client)[_-]?key|credential)(?:[\w-]|\.(?!\w{1,8}:\d)){0,64}(?:\\?[\"'])?\s*(?:=|:(?!:))\s*)"
        r"(\\?\"[^\n]*?\"(?=\s*[,}\]]|\s*$)|\\?\"[^\n]*|'[^'\n]*'|'[^\n]*|[^\s\"',;&}]+)"
    ), 1),
]

_SECRET_KEY = re.compile(
    r"(?i)secret|password|passwd|token|api[_-]?key|authorization|cookie|private[_-]?key|credential|^(?:auth|pass)$"
    r"|(?:access|account|client|master|encryption|signing|session|license|storage)[_-]?key"
)


def redact_text(text: str) -> str:
    for kind, pattern, keep in _PATTERNS:
        tag = f"[REDACTED:{kind}]"
        if keep is None:
            text = pattern.sub(tag, text)
        elif kind == "url":
            text = pattern.sub(lambda m: m.group(1) + tag + "@", text)
        else:
            text = pattern.sub(lambda m: m.group(1) + tag, text)
    return text.replace(str(Path.home()), "~")


def redact(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {
            k: "[REDACTED:key]" if _SECRET_KEY.search(str(k)) and v is not None else redact(v)
            for k, v in value.items()
        }
    return value
