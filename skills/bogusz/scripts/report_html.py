"""Render a redacted Bogusz Markdown report as one self-contained HTML page next to it.

Converts only the Markdown the report templates use. Every text node is escaped, the page loads nothing from the
network, and local screenshots are embedded as data URIs so the file can be sent on its own.
"""

import base64
import hashlib
import html
import re
import sys
from pathlib import Path

PILLS = {"passed", "failed", "skipped", "blocked", "not run", "covered", "partial", "missing", "n/a",
         "confirmed", "not reproduced", "not tested"}
STATUS_ORDER = ["passed", "failed", "skipped", "blocked", "not run"]
INLINE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*"
                    r"|\[(not run|interpretation|assumption|guess|REDACTED:\w+)\]")
BLOCK_START = re.compile(r"#{1,4} |```|\||>|\s*(?:[-*]|\d+\.) ")


def esc(s):
    return html.escape(s, quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def image_mime(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def embed(path, base):
    """An <img> with the file inlined, or None when path is not a readable image file."""
    path = path.strip()
    if not re.search(r"\.(png|jpe?g|gif|webp)$", path, re.I):
        return None
    p = Path(path).expanduser()
    p = p if p.is_absolute() else base / p
    if not p.is_file():
        return None
    data = p.read_bytes()
    mime = image_mime(data)  # only real images go in, so a misnamed text file never lands in the page
    if not mime:
        return None
    src = "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())
    return '<img class="shot" src="%s" alt="%s" title="%s">' % (src, esc(p.name), esc(path))


def safe_href(url):
    return re.match(r"(https?://|#|[^:]*$)", url) is not None


def inline_text(s, base):
    out, pos = [], 0
    for m in INLINE.finditer(s):
        out.append(esc(s[pos:m.start()]))
        pos = m.end()
        alt, src, text, href, bold, tag = m.groups()
        if src is not None:
            out.append(embed(src, base) or esc(m.group(0)))
        elif text is not None:
            out.append('<a href="%s">%s</a>' % (esc(href), esc(text)) if safe_href(href) else esc(text))
        elif bold is not None:
            out.append("<strong>%s</strong>" % esc(bold))
        else:
            kind = "nr" if tag == "not run" else "red" if tag.startswith("REDACTED") else "int"
            out.append('<span class="t %s">%s</span>' % (kind, esc(m.group(0))))
    out.append(esc(s[pos:]))
    return "".join(out)


def inline(s, base):
    out = []
    for i, part in enumerate(re.split(r"(`[^`]*`)", s)):
        if i % 2 == 0:
            out.append(inline_text(part, base))
            continue
        code = part[1:-1]
        kind = ("ran" if code.startswith("[ran:") else "nr" if code.startswith("[not run")
                else "int" if code.startswith(("[interpretation", "[assumption")) else "")
        out.append(embed(code, base) or ('<code class="t %s">' % kind if kind else "<code>") + esc(code) + "</code>")
    return "".join(out)


def cells(line):
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    out, cur, in_code, i = [], "", False, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and s[i + 1:i + 2] == "|":
            cur, i = cur + "|", i + 2
            continue
        if c == "`":
            in_code = not in_code
        if c == "|" and not in_code:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
        i += 1
    out.append(cur.strip())
    return out


def cell_html(c, base):
    if c.lower() in PILLS:
        return '<span class="st %s">%s</span>' % (slug(c), esc(c))
    return embed(c, base) or inline(c, base)


def render(md, base):
    """Returns (title, meta, body_html, nav, status_counts)."""
    lines = re.sub(r"<!--.*?-->", "", md, flags=re.S).splitlines()
    title, meta, out, nav, counts = "Bogusz report", "", [], [], {}
    sec, ids, i = None, set(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>%s</code></pre>" % esc("\n".join(lines[i + 1:j])))
            i = j + 1
        elif re.match(r"#{1,4} ", line):
            level, text = len(line) - len(line.lstrip("#")), line.lstrip("#").strip()
            i += 1
            if level == 1:
                m = re.match(r"(.*\S)\s+\(([^()]*)\)$", text)  # the last "(date, repo@sha)" group
                title, meta = (m.group(1), m.group(2)) if m else (text, "")
            elif level == 2:
                sid = slug(text)
                while sid in ids:
                    sid += "-2"
                ids.add(sid)
                sec = [sid, text, 0]
                nav.append(sec)
                cls = ""
                if text == "Verdict":
                    nxt = next((l for l in lines[i:] if l.strip()), "")
                    word = re.match(r"\W*(\w*)", nxt).group(1).lower()
                    cls = ' class="verdict %s"' % esc(word)
                out.append('%s<section id="%s"%s><h2>%s</h2>' % ("</section>" if len(nav) > 1 else "", sid, cls,
                                                                inline(text, base)))
            else:
                out.append("<h%d>%s</h%d>" % (level, inline(text, base), level))
        elif line.startswith("|") and i + 1 < len(lines) and re.match(r"\s*\|?\s*:?-{3,}", lines[i + 1]):
            head = cells(line)
            col = next((k for k, h in enumerate(head) if h.lower() == "status"), None)
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            seen = []
            body = []
            for r in rows:
                s = r[col].lower() if col is not None and col < len(r) else ""
                if col is not None:
                    counts[s] = counts.get(s, 0) + 1
                    seen += [] if s in seen else [s]
                body.append('<tr%s>%s</tr>' % (' data-s="%s"' % esc(s) if s else "",
                                               "".join("<td>%s</td>" % cell_html(c, base) for c in r)))
            if sec:
                sec[2] += len(rows)
            if col is not None and len(seen) > 1:
                out.append('<div class="filters" role="group" aria-label="Filter rows"><button aria-pressed="true">'
                           'All %d</button>%s</div>' % (len(rows), "".join(
                               '<button aria-pressed="false" data-s="%s">%s</button>' % (esc(s), esc(s)) for s in seen)))
            out.append('<div class="tbl"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
                "".join('<th scope="col">%s</th>' % inline(h, base) for h in head), "".join(body)))
        elif re.match(r"\s*(?:[-*]|\d+\.) ", line):
            tag = "ol" if re.match(r"\s*\d+\.", line) else "ul"
            items = []
            while i < len(lines) and lines[i].strip() and (not BLOCK_START.match(lines[i]) or
                                                            re.match(r"\s*(?:[-*]|\d+\.) ", lines[i])):
                item = re.match(r"(\s*)(?:[-*]|\d+\.) (.*)", lines[i])
                if item and (not item.group(1) or not items):
                    items.append(inline(item.group(2), base))
                else:  # continuation or nested item: keep it with the item above
                    items[-1] += "<br>" + inline(lines[i].strip(), base)
                i += 1
            if sec:
                sec[2] += len(items)
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % it for it in items), tag))
        elif line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(inline(lines[i].lstrip("> "), base))
                i += 1
            out.append("<blockquote>%s</blockquote>" % "<br>".join(quote))
        else:
            para, i = [inline(line, base)], i + 1
            while i < len(lines) and lines[i].strip() and not BLOCK_START.match(lines[i]):
                para.append(inline(lines[i], base))
                i += 1
            out.append("<p>%s</p>" % "<br>".join(para))
    if nav:
        out.append("</section>")
    return title, meta, "\n".join(out), nav, counts


CSS = """
:root{--bg:#f6f7f9;--surface:#fff;--ink:#16202c;--muted:#5a6676;--line:#dde2e8;--accent:#2457c5;--accent-soft:#e7eefc;
--pass:#17803d;--pass-soft:#e3f4e8;--fail:#c0322b;--fail-soft:#fbe7e5;--warn:#9a6200;--warn-soft:#fdf1d8;
--idle:#5d6b7c;--idle-soft:#eceff3;--code:#eef1f5;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#0f141a;--surface:#161d26;--ink:#e4e9ef;--muted:#9aa6b4;--line:#2a3440;
--accent:#7aa2ff;--accent-soft:#1d2a44;--pass:#5fd08a;--pass-soft:#163322;--fail:#ff8a80;--fail-soft:#3a1b1a;
--warn:#f0bf5a;--warn-soft:#3a2c10;--idle:#a3afbd;--idle-soft:#222b36;--code:#1f2833;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 var(--sans);display:grid;grid-template-columns:220px minmax(0,1fr)}
nav{position:sticky;top:0;height:100vh;overflow:auto;border-right:1px solid var(--line);padding:24px 14px;font-size:.88rem}
nav b{display:block;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 8px 10px}
nav a{display:flex;justify-content:space-between;gap:8px;color:var(--muted);text-decoration:none;padding:5px 8px;border-radius:5px}
nav a:hover{background:var(--surface);color:var(--ink)}
nav small{font-family:var(--mono)}
main{padding:28px clamp(16px,4vw,48px) 64px;display:grid;gap:22px;min-width:0;max-width:1200px}
h1{font-size:1.6rem;line-height:1.25;margin:0;text-wrap:balance}
.meta{font:.85rem var(--mono);color:var(--muted);margin-top:4px}
h2{font-size:1.15rem;margin:0 0 10px}
h3,h4{font-size:1rem;margin:16px 0 8px}
section{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px 20px;min-width:0;scroll-margin-top:16px}
section>:last-child{margin-bottom:0}
p,ul,ol{margin:0 0 10px}
li{margin-bottom:4px}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
code{font:.85em var(--mono);background:var(--code);padding:.1em .35em;border-radius:4px;overflow-wrap:anywhere}
pre{background:var(--code);padding:12px 14px;border-radius:8px;overflow-x:auto;font-size:.85rem}
pre code{background:none;padding:0;overflow-wrap:normal}
blockquote{margin:0;border-left:3px solid var(--line);padding-left:12px;color:var(--muted)}
.verdict{border-width:2px}
.verdict.passed{border-color:var(--pass);background:var(--pass-soft)}
.verdict.failed{border-color:var(--fail);background:var(--fail-soft)}
.verdict.inconclusive{border-color:var(--warn);background:var(--warn-soft)}
.verdict p{font-size:1.02rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 14px}
.kpi b{display:block;font-size:1.6rem;line-height:1.1;font-variant-numeric:tabular-nums}
.kpi span{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.kpi.passed b{color:var(--pass)}.kpi.failed b{color:var(--fail)}.kpi.blocked b{color:var(--warn)}
.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;background:var(--idle-soft);margin-top:10px}
.bar i.passed{background:var(--pass)}.bar i.failed{background:var(--fail)}.bar i.blocked{background:var(--warn)}
.bar i.skipped,.bar i.not-run{background:var(--idle)}
.tbl{overflow-x:auto;border:1px solid var(--line);border-radius:8px;margin-bottom:10px}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;vertical-align:top;padding:8px 12px;border-bottom:1px solid var(--line)}
tbody tr:last-child td{border-bottom:0}
th{font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:var(--bg)}
td:first-child{font:600 .82rem var(--mono);white-space:nowrap}
.st{display:inline-flex;align-items:center;gap:5px;font-size:.75rem;font-weight:600;line-height:1;padding:4px 8px;border-radius:999px;white-space:nowrap;background:var(--idle-soft);color:var(--idle)}
.st::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.st.passed,.st.covered,.st.confirmed{background:var(--pass-soft);color:var(--pass)}
.st.failed,.st.missing{background:var(--fail-soft);color:var(--fail)}
.st.blocked,.st.partial{background:var(--warn-soft);color:var(--warn)}
.st.not-run::before,.st.skipped::before,.st.n-a::before,.st.not-tested::before{background:none;border:1.5px solid currentColor;width:5px;height:5px}
.t.ran{color:var(--pass)}.t.nr{color:var(--idle)}.t.int{color:var(--warn)}.t.red{color:var(--fail);font-family:var(--mono)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
.filters button{font:500 .8rem var(--sans);color:var(--ink);background:var(--surface);border:1px solid var(--line);padding:5px 10px;border-radius:6px;cursor:pointer}
.filters button[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-soft)}
img.shot{max-width:240px;border:1px solid var(--line);border-radius:6px;cursor:zoom-in;display:block}
img.shot.zoom{position:fixed;inset:0;margin:auto;max-width:96vw;max-height:96vh;z-index:9;cursor:zoom-out;box-shadow:0 0 0 100vmax rgba(0,0,0,.7)}
@media (max-width:760px){body{grid-template-columns:1fr}nav{display:none}}
@media print{body{display:block;background:#fff}nav,.filters{display:none}section{break-inside:avoid-page;border-color:#ccc}tr[hidden]{display:table-row}}
"""

JS = """document.querySelectorAll('.filters').forEach(f=>f.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
f.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));
f.nextElementSibling.querySelectorAll('tbody tr').forEach(r=>{r.hidden=!!b.dataset.s&&r.dataset.s!==b.dataset.s})}));
document.addEventListener('click',e=>{if(e.target.classList.contains('shot'))e.target.classList.toggle('zoom')});"""


def page(md, base):
    title, meta, body, nav, counts = render(md, base)
    total = sum(counts.values())
    kpis = ""
    if total:
        counts.setdefault("failed", 0)  # "0 failed" is worth a tile of its own
        order = [s for s in STATUS_ORDER if s in counts] + [s for s in counts if s not in STATUS_ORDER]
        tiles = ['<div class="kpi"><b>%d</b><span>Cases</span></div>' % total]
        tiles += ['<div class="kpi %s"><b>%d</b><span>%s</span></div>' % (slug(s), counts[s], esc(s or "no status"))
                  for s in order]
        bar = "".join('<i class="%s" style="width:%.2f%%"></i>' % (slug(s), 100.0 * counts[s] / total) for s in order)
        label = ", ".join("%d %s" % (counts[s], s or "no status") for s in order)
        kpis = '<div><div class="kpis">%s</div><div class="bar" role="img" aria-label="%s">%s</div></div>' % (
            "".join(tiles), esc(label), bar)
    links = "".join('<a href="#%s">%s%s</a>' % (sid, esc(text), "<small>%d</small>" % n if n else "")
                    for sid, text, n in nav)
    script_hash = base64.b64encode(hashlib.sha256(JS.encode()).digest()).decode()
    csp = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'sha256-%s'" % script_hash
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="%s">
<title>%s</title><style>%s</style></head>
<body><nav aria-label="Report sections"><b>Bogusz report</b>%s</nav>
<main><header><h1>%s</h1><div class="meta">%s</div></header>%s
%s</main><script>%s</script></body></html>
""" % (csp, esc(title), CSS, links, esc(title), esc(meta), kpis, body, JS)


if __name__ == "__main__":
    src = Path(sys.argv[1]).expanduser()
    dst = src.with_suffix(".html")
    dst.write_text(page(src.read_text(), src.parent))
    print(dst)
