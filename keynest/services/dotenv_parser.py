"""A small, conservative ``.env`` parser and serializer (no third-party deps).

Supports the common subset of ``.env`` syntax:

* ``KEY=value`` lines
* optional ``export KEY=value`` prefix
* single- and double-quoted values
* ``#`` comments on their own line or after an unquoted value
* blank lines

It does *not* attempt variable interpolation (``${OTHER}``); such values are
kept literally so secrets round-trip exactly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from keynest.model import key_warning, value_warnings


@dataclass
class DotenvParseResult:
    """The outcome of parsing a ``.env`` file."""

    values: dict[str, str]
    warnings: list[str]


def _strip_inline_comment(value: str) -> str:
    """Strip an unquoted trailing ``# comment`` from a value."""
    result_chars: list[str] = []
    in_single = in_double = False
    for ch in value:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            break
        result_chars.append(ch)
    return "".join(result_chars).strip()


def _split_quoted(value: str) -> str:
    """Return the contents of a leading quoted string, ignoring trailing text.

    ``value`` is known to start with a quote. Everything after the matching
    closing quote (e.g. an inline ``# comment``) is discarded.
    """
    quote = value[0]
    out: list[str] = []
    i = 1
    while i < len(value):
        ch = value[i]
        if quote == '"' and ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", '"': '"', "\\": "\\"}.get(nxt, "\\" + nxt))
            i += 2
            continue
        if ch == quote:
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _unquote(value: str) -> str:
    """Remove surrounding quotes (and any trailing inline comment) if present."""
    if value and value[0] in "\"'":
        return _split_quoted(value)
    return value


def parse_dotenv(text: str) -> DotenvParseResult:
    """Parse ``.env`` ``text`` into a values dict plus a list of warnings.

    Args:
        text: The full contents of a ``.env`` file.

    Returns:
        A :class:`DotenvParseResult`.
    """
    values: dict[str, str] = {}
    warnings: list[str] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            warnings.append(f"Line {lineno}: no '=' found, skipped.")
            continue
        key, _, rest = line.partition("=")
        key = key.strip()
        rest = rest.strip()
        quoted = bool(rest) and rest[0] in "\"'"
        value = _unquote(rest) if quoted else _strip_inline_comment(rest)
        if not key:
            warnings.append(f"Line {lineno}: empty key, skipped.")
            continue
        if key in values:
            warnings.append(f"Line {lineno}: duplicate key {key!r} overrides earlier value.")
        kw = key_warning(key)
        if kw:
            warnings.append(f"Line {lineno}: {kw}")
        for vw in value_warnings(value):
            warnings.append(f"Line {lineno}: {key}: {vw}")
        values[key] = value
    return DotenvParseResult(values=values, warnings=warnings)


def parse_dotenv_file(path: str) -> DotenvParseResult:
    """Parse the ``.env`` file at ``path``."""
    with open(path, encoding="utf-8") as handle:
        return parse_dotenv(handle.read())


def _quote_if_needed(value: str) -> str:
    """Double-quote a value if it contains whitespace, quotes, ``#``, or newlines."""
    needs_quotes = any(ch.isspace() for ch in value) or any(ch in value for ch in "#\"'")
    if "\n" in value or "\r" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
        return f'"{escaped}"'
    if needs_quotes:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def serialize_dotenv(values: Mapping[str, object]) -> str:
    """Serialize a values mapping into ``.env`` text (sorted by key).

    Args:
        values: A mapping of keys to scalar values.

    Returns:
        The ``.env`` file contents, ending with a trailing newline.
    """
    lines = [f"{key}={_quote_if_needed(str(values[key]))}" for key in sorted(values)]
    return "\n".join(lines) + ("\n" if lines else "")
