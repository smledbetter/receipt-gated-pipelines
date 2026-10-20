"""Package-name normalisation and mention finding."""
import json
import re

_VERSION_TAIL = re.compile(r"[@ ]v?\d[\w.\-+]*.*$")
_PAREN_TAIL = re.compile(r"\s*\(.*\)\s*$")
_ODD_HYPHENS = re.compile("[‐‑‒–−]")


def normalize_text(text):
    """Map typographic hyphens and non-breaking spaces to ASCII so that
    'node‑fetch' (U+2011) matches 'node-fetch'. Mercury writes these often."""
    if not text:
        return text or ""
    return _ODD_HYPHENS.sub("-", text).replace(" ", " ").replace("：", ":")


def normalize(raw):
    """Reduce a model-written package reference to a bare lower-case name.

    "commons-text@1.9 (maven)" -> "commons-text"
    "`lodash` 4.17.20"          -> "lodash"
    "org.apache.logging.log4j:log4j-core" -> "log4j-core"
    """
    if not isinstance(raw, str):
        return ""
    s = raw.strip().strip("`'\"*").strip()
    s = _PAREN_TAIL.sub("", s)
    s = _VERSION_TAIL.sub("", s)
    s = s.strip().strip("`'\"*:,;").strip()
    if ":" in s:  # maven coordinates
        s = s.split(":")[-1]
    return s.lower()


class DepIndex:
    """Lookup from any spelling of a dependency to its canonical lower-case name."""

    def __init__(self, deps):
        self.deps = deps
        self.names = [d["name"].lower() for d in deps]
        self.by_name = {d["name"].lower(): d for d in deps}
        self.alias = {}
        for d in deps:
            self.alias[d["name"].lower()] = d["name"].lower()
            if d.get("osv_name"):
                self.alias[d["osv_name"].lower()] = d["name"].lower()
                self.alias[d["osv_name"].split(":")[-1].lower()] = d["name"].lower()
        self._patterns = {
            n: re.compile(r"(?<![a-z0-9_.\-])" + re.escape(n) + r"(?![a-z0-9_\-])", re.I)
            for n in self.names
        }

    def canonical(self, raw):
        n = normalize(normalize_text(raw))
        return self.alias.get(n)

    def mentions(self, text):
        """Return {name: [line_index, ...]} for every dependency named in text."""
        out = {}
        lines = normalize_text(text).split("\n")
        for n, pat in self._patterns.items():
            hits = [i for i, line in enumerate(lines) if pat.search(line)]
            if hits:
                out[n] = hits
        return out

    def mentioned(self, text, name):
        return bool(self._patterns[name].search(normalize_text(text)))

    def mask(self, text):
        """Replace every dependency name with PKG so cue words inside names
        ('safe-buffer', 'secure-random') do not read as outcomes."""
        t = normalize_text(text)
        for n in sorted(self.names, key=len, reverse=True):
            t = self._patterns[n].sub("PKG", t)
        return t


def called_packages(record):
    """Packages with a call-log entry (the shim ran them, with or without error)."""
    return {c["request_args"]["package_name"].lower() for c in record.get("call_log", [])}


def attempted_packages(record, index):
    """Packages the model asked for in any tool call, including calls whose
    arguments the harness could not parse (those never reached the call log)."""
    out = set()
    for m in record.get("transcript", []):
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            args = (tc.get("function") or {}).get("arguments")
            name = None
            if isinstance(args, dict):
                name = args.get("package_name") or args.get("name") or args.get("package")
            elif isinstance(args, str):
                try:
                    d = json.loads(args)
                    name = d.get("package_name") or d.get("name") or d.get("package")
                except (json.JSONDecodeError, AttributeError):
                    mm = re.search(r'"(?:package_name|name|package)"\s*:\s*"([^"]*)', args)
                    name = mm.group(1) if mm else None
            if name:
                c = index.canonical(name)
                if c:
                    out.add(c)
    return out


def tool_summaries(record):
    """Advisory summaries the tool returned, keyed by package. Used to spot
    package names that only appear inside another package's advisory text."""
    out = {}
    for m in record.get("transcript", []):
        if m.get("role") != "tool":
            continue
        try:
            c = json.loads(m.get("content") or "")
        except json.JSONDecodeError:
            continue
        if not isinstance(c, dict) or not c.get("package"):
            continue
        texts = [v.get("summary", "") for v in c.get("vulnerabilities", []) if isinstance(v, dict)]
        out.setdefault(c["package"].lower(), []).extend(t for t in texts if t)
    return out
