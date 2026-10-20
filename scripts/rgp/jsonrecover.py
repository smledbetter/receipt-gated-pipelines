"""Tolerant JSON extraction for model-written reports.

Models wrap JSON in prose and code fences, add // and /* */ comments, put
ellipses inside arrays, and get cut off by the output-token cap. The shipped
parsers gave up on all of these. This module recovers what it can and says
whether the text was truncated.
"""
import json
import re

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
_ELLIPSIS_ITEM = re.compile(
    r",?\s*(?:\.\.\.|…)[^\]\}\n,]*(?=[,\]\}\n])"  # ... or … followed by optional note
)
_LINE_COMMENT = re.compile(r"(?<![:\"'\w])//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_TRAILING_COMMA = re.compile(r",\s*([\]\}])")


def candidates(text):
    """Yield JSON-looking substrings, largest first: fenced blocks, then the
    span from the first '{' to the last '}', then the first '{' to the end."""
    seen = set()
    for m in _FENCE.finditer(text):
        body = m.group(1).strip()
        if body and body not in seen:
            seen.add(body)
            yield body
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j > i:
        body = text[i:j + 1]
        if body not in seen:
            seen.add(body)
            yield body
    if i != -1:
        body = text[i:]
        if body not in seen:
            yield body


def clean(s):
    s = _BLOCK_COMMENT.sub("", s)
    s = _LINE_COMMENT.sub("", s)
    s = _ELLIPSIS_ITEM.sub("", s)
    s = _TRAILING_COMMA.sub(r"\1", s)
    return s


def close_open(s):
    """Append whatever closes the open strings, arrays and objects in s.
    Drops a dangling partial key/value first so the result parses."""
    # Cut back to the last complete value boundary: a comma, '{' or '['.
    stack = []
    in_str = False
    esc = False
    last_boundary = 0
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
            last_boundary = i + 1
        elif ch in "}]":
            if stack:
                stack.pop()
            last_boundary = i + 1
        elif ch == ",":
            last_boundary = i + 1
    head = s[:last_boundary].rstrip().rstrip(",")
    # Recompute the stack for the head.
    stack = []
    in_str = False
    esc = False
    for ch in head:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    tail = "".join("}" if c == "{" else "]" for c in reversed(stack))
    return head + tail


def parse(text):
    """Return (obj, info). obj is None when nothing parses.

    info["truncated"] is True when the object only parsed after closing open
    brackets, which means the text was cut off. info["cleaned"] is True when
    comments, ellipses or trailing commas had to be removed first.
    """
    for cand in candidates(text):
        start = text.find(cand)
        span = (start, start + len(cand)) if start != -1 else None
        for cleaned_flag, body in ((False, cand), (True, clean(cand))):
            try:
                obj = json.loads(body)
                if isinstance(obj, (dict, list)):
                    return obj, {"truncated": False, "cleaned": cleaned_flag, "span": span}
            except json.JSONDecodeError:
                pass
        try:
            obj = json.loads(close_open(clean(cand)))
            if isinstance(obj, (dict, list)) and obj:
                return obj, {"truncated": True, "cleaned": True, "span": span}
        except json.JSONDecodeError:
            continue
    return None, {"truncated": False, "cleaned": False, "span": None}


def is_cut_off(text):
    """Heuristic: the report ends inside an unclosed JSON structure."""
    i = text.find("{")
    if i == -1:
        return False
    depth = 0
    in_str = False
    esc = False
    for ch in text[i:]:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return depth > 0 or in_str
