"""Claude Code command-file parsing and argument rendering (self-contained).

This module is deliberately standard-library-only and has NO relative imports:
it is copied byte-for-byte into every generated Hermes command adapter, and its
SHA-256 is recorded in each Capability Passport. Changing this file invalidates
every adapter's verification evidence (see update_reconciliation.py).

Source semantics implemented here follow the public Claude Code documentation
"Extend Claude with skills" (https://code.claude.com/docs/en/slash-commands),
fetched 2026-11-07, SHA-256 of the fetched markdown
977bb9f8d6a004c37e6731afd94bc3ad7bba1e64a2b2d7e7f22df910d4b06287. That page
states that `.claude/commands/*.md` files and skills share the same frontmatter
(except `name`/`paths`) and the same `$ARGUMENTS` substitution rules.

Nothing here executes the source command, its `!` shell injections, or any
tool. Where the documentation leaves behavior open, the renderer FAILS CLOSED
(refuses) rather than guessing, and the analyzer reports the ambiguity.
"""
from __future__ import annotations

import hashlib
import re

SEMANTICS_VERSION = 'claude-code-command-args/2026-11-07'
SEMANTICS_SOURCE = 'https://code.claude.com/docs/en/slash-commands'
SEMANTICS_SOURCE_SHA256 = '977bb9f8d6a004c37e6731afd94bc3ad7bba1e64a2b2d7e7f22df910d4b06287'

MAX_TEMPLATE_CHARS = 120_000
MAX_ARGS_CHARS = 6_000
# Documented placeholder text Claude Code itself uses when
# `disableSkillShellExecution` is on. Reusing it means our rendering of a
# shell-injection command equals Claude Code's documented *disabled* mode
# (not its default mode, which executes the command).
SHELL_DISABLED_PLACEHOLDER = '[shell command execution disabled by policy]'
# Claude: "appends them as `ARGUMENTS: <value>`". The separator before it is
# not documented; this two-newline separator is an assumption (reported).
APPEND_SEPARATOR = '\n\n'

KNOWN_FRONTMATTER = {
    # key: how a Hermes native command adapter can treat it
    'description': 'preserved',
    'argument-hint': 'preserved',
    'arguments': 'preserved',
    'disable-model-invocation': 'preserved',
    'user-invocable': 'preserved',
    'when_to_use': 'metadata_only',
    'allowed-tools': 'not_preservable_preapproval',
    'disallowed-tools': 'not_enforceable_restriction',
    'model': 'not_preservable',
    'effort': 'not_preservable',
    'context': 'not_preservable_execution_model',
    'agent': 'not_preservable_execution_model',
    'hooks': 'not_preservable_executable',
    'shell': 'not_applicable_shell_disabled',
    'license': 'metadata_only',
    'compatibility': 'metadata_only',
    'metadata': 'metadata_only',
}
_KEY = re.compile(r'^([A-Za-z_][A-Za-z0-9_-]*)\s*:(.*)$')
_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')
# Shell metacharacters for which "shell-style quoting" may diverge between a
# real shell parser and our minimal tokenizer. Indexed/named rendering refuses
# argument strings containing any of them (fail closed).
_AMBIGUOUS_ARG_CHARS = set('\\$`|&;<>()*?[]{}~#!\n\r\t')


class CommandFormatError(ValueError):
    """The source command cannot be parsed without guessing."""


class ArgumentRenderRefused(ValueError):
    """Caller arguments cannot be rendered with documented semantics."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _scalar(raw: str):
    value = raw.strip()
    if value == '':
        return ''
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        inner = value[1:-1]
        if value[0] == '"' and ('\\' in inner):
            raise CommandFormatError('Escaped double-quoted YAML scalar is not supported')
        return inner.replace("''", "'") if value[0] == "'" else inner
    if value in {'true', 'True', 'TRUE'}:
        return True
    if value in {'false', 'False', 'FALSE'}:
        return False
    if value[0] in '|>{&*!%@`':
        raise CommandFormatError('Unsupported YAML construct in frontmatter')
    if value.startswith('['):
        if not value.endswith(']'):
            raise CommandFormatError('Unterminated YAML flow list')
        inner = value[1:-1].strip()
        if not inner:
            return []
        if '[' in inner or '{' in inner:
            raise CommandFormatError('Nested YAML flow collections are not supported')
        return [_scalar(x) for x in inner.split(',')]
    return value


def parse_frontmatter(text: str) -> tuple[dict, str, list[str]]:
    """Return (frontmatter, body, unparsed_keys) for a restricted YAML subset.

    Supports `key: scalar`, `key: [a, b]` and block lists. Anything else is a
    CommandFormatError (never a guess). Body is returned byte-exact after the
    closing `---` line.
    """
    if _CONTROL.search(text.replace('\t', '').replace('\r\n', '')):
        raise CommandFormatError('Control characters in command file')
    normalized = text[1:] if text.startswith('\ufeff') else text
    if not (normalized.startswith('---\n') or normalized.startswith('---\r\n')):
        return {}, normalized, []
    lines = normalized.splitlines(keepends=True)
    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip('\r\n') == '---':
            end = i
            break
    if end is None:
        raise CommandFormatError('Frontmatter opened with --- but never closed')
    meta: dict = {}
    unparsed: list[str] = []
    current_list_key = None
    for raw in lines[1:end]:
        line = raw.rstrip('\r\n')
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith((' ', '\t')) or line.startswith('-'):
            stripped = line.strip()
            if current_list_key is not None and stripped.startswith('- '):
                meta[current_list_key].append(_scalar(stripped[2:]))
                continue
            if current_list_key is not None and stripped == '-':
                raise CommandFormatError('Empty YAML list item')
            raise CommandFormatError('Nested YAML structure is not supported')
        m = _KEY.match(line)
        if not m:
            raise CommandFormatError('Unparseable frontmatter line')
        key, rest = m.group(1), m.group(2)
        if key in meta:
            raise CommandFormatError('Duplicate frontmatter key: ' + key)
        if rest.strip() == '':
            meta[key] = []
            current_list_key = key
            continue
        current_list_key = None
        try:
            meta[key] = _scalar(rest)
        except CommandFormatError:
            unparsed.append(key)
            meta[key] = None
    body = ''.join(lines[end + 1:])
    return meta, body, unparsed


def declared_argument_names(meta: dict) -> list[str]:
    raw = meta.get('arguments')
    if raw is None or raw == '' or raw == []:
        return []
    if isinstance(raw, str):
        names = raw.split()
    elif isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        names = [x.strip() for x in raw]
    else:
        raise CommandFormatError('Invalid `arguments` frontmatter')
    for n in names:
        if not _NAME.fullmatch(n) or n == 'ARGUMENTS' or n.isdigit():
            raise CommandFormatError('Invalid declared argument name')
    if len(set(names)) != len(names):
        raise CommandFormatError('Duplicate declared argument name')
    return names


# --- placeholder scanning -------------------------------------------------

def _placeholder_regex(names: list[str]):
    named = ''
    if names:
        # Longest first so `$issue_id` is preferred over `$issue`.
        named = '|(?P<named>' + '|'.join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r')(?![A-Za-z0-9_])'
    return re.compile(
        r'(?P<bs>\\*)\$(?:ARGUMENTS\[(?P<aidx>\d+)\]|(?P<all>ARGUMENTS)(?![A-Za-z0-9_\[])|(?P<idx>\d+)'
        + named + ')')


def scan_placeholders(body: str, names: list[str]) -> dict:
    """Count placeholders and forms whose documented meaning is ambiguous."""
    rx = _placeholder_regex(names)
    out = {'all': 0, 'indexed': 0, 'named': 0, 'escaped': 0, 'ambiguous': []}
    for m in rx.finditer(body):
        bs = len(m.group('bs'))
        if bs == 1:
            out['escaped'] += 1
            continue
        if bs > 2:
            out['ambiguous'].append('three_or_more_backslashes_before_placeholder')
        if m.group('all'):
            out['all'] += 1
        elif m.group('aidx') is not None or m.group('idx') is not None:
            digits = m.group('aidx') if m.group('aidx') is not None else m.group('idx')
            out['indexed'] += 1
            if len(digits) > 1:
                out['ambiguous'].append('multi_digit_index_$' + digits)
        else:
            out['named'] += 1
    # `$ARGUMENTSfoo` / `$ARGUMENTS[x]` with a non-digit: undocumented.
    if re.search(r'\$ARGUMENTS(?:[A-Za-z0-9_]|\[(?!\d+\]))', body):
        out['ambiguous'].append('ARGUMENTS_followed_by_identifier_or_bracket')
    out['ambiguous'] = sorted(set(out['ambiguous']))
    return out


def likely_unintended_placeholders(body: str) -> list[str]:
    """Heuristic warnings only (e.g. `$1,500` money amounts) — never rewritten."""
    hits = []
    for m in re.finditer(r'(?<!\\)\$(\d+)(?=[,.]\d)', body):
        hits.append('currency_like_$' + m.group(1))
    return sorted(set(hits))


# --- shell injection ------------------------------------------------------

_INLINE_SHELL = re.compile(r'(?:(?<=\s)|^)[!]`([^`\n]+)`', re.M)
_SHELL_FENCE_OPEN = re.compile(r'^(\s{0,3})(`{3,})!\s*$')
# Hermes' own `skills.inline_shell` preprocessor matches !`...` ANYWHERE.
HERMES_INLINE_SHELL = re.compile(r'[!]`([^`\n]+)`')


def find_shell_injections(body: str) -> dict:
    lines = body.splitlines(keepends=True)
    blocks = 0
    i = 0
    while i < len(lines):
        m = _SHELL_FENCE_OPEN.match(lines[i].rstrip('\r\n'))
        if m:
            blocks += 1
            fence = m.group(2)
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(fence):
                j += 1
            i = j + 1
            continue
        i += 1
    return {'inline': len(_INLINE_SHELL.findall(body)), 'fenced_blocks': blocks,
            'hermes_inline_shell_patterns': len(HERMES_INLINE_SHELL.findall(body))}


def disable_shell_injections(body: str) -> str:
    """Replace Claude `!` injections with Claude's documented disabled placeholder.

    Fenced ```! blocks become ONE placeholder per block (whether Claude emits one
    per command line is undocumented; reported as an assumption). Also defuses
    every remaining `!`...`` occurrence so Hermes' `skills.inline_shell`
    preprocessor (which matches anywhere) can never execute source text.
    """
    lines = body.splitlines(keepends=True)
    out = []
    i = 0
    while i < len(lines):
        m = _SHELL_FENCE_OPEN.match(lines[i].rstrip('\r\n'))
        if m:
            fence = m.group(2)
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(fence):
                j += 1
            ending = '\n' if (j < len(lines) and lines[j].endswith('\n')) or lines[i].endswith('\n') else ''
            out.append(SHELL_DISABLED_PLACEHOLDER + ending)
            i = j + 1
            continue
        out.append(lines[i])
        i += 1
    text = ''.join(out)
    text = _INLINE_SHELL.sub(SHELL_DISABLED_PLACEHOLDER, text)
    # Anything still matching Hermes' looser pattern is literal in Claude but
    # would execute under Hermes inline_shell: break the trigger, keep text.
    return HERMES_INLINE_SHELL.sub(lambda m: '!\u2060`' + m.group(1) + '`', text)


# --- argument rendering ---------------------------------------------------

def split_arguments(raw: str) -> list[str]:
    """Minimal shell-style split: whitespace, '...' and "..." only.

    Documented: `/my-skill "hello world" second` -> ['hello world', 'second'] and
    a quoted `"$ARGUMENTS from yesterday"` is inserted literally. Everything a
    real shell parser might treat differently is REFUSED: escapes, backticks,
    and (outside quotes) expansions, operators and globs, plus unbalanced quotes.
    """
    out, cur, quote, has_token = [], [], None, False
    for c in raw:
        if c in '\\`\n\r\t':
            raise ArgumentRenderRefused('Arguments contain escapes/backticks/tabs/newlines; quoting semantics undocumented')
        if quote:
            if c == quote:
                quote = None
            else:
                cur.append(c)
            continue
        if c in '"\'':
            quote = c
            has_token = True
        elif c == ' ':
            if has_token:
                out.append(''.join(cur))
                cur, has_token = [], False
        elif c in _AMBIGUOUS_ARG_CHARS:
            raise ArgumentRenderRefused('Unquoted shell metacharacter ' + repr(c) + ' in arguments; quoting semantics undocumented')
        else:
            cur.append(c)
            has_token = True
    if quote:
        raise ArgumentRenderRefused('Unbalanced quote in arguments')
    if has_token:
        out.append(''.join(cur))
    return out


def render(body: str, raw_args: str, names: list[str] | None = None) -> dict:
    """Render a command body with documented Claude Code `$ARGUMENTS` semantics.

    Returns {'text', 'received', 'appended', 'argv'}; raises
    ArgumentRenderRefused instead of guessing. Single pass: argument values are
    inserted literally and never re-scanned.
    """
    names = list(names or [])
    if not isinstance(raw_args, str) or len(raw_args) > MAX_ARGS_CHARS:
        raise ArgumentRenderRefused('Arguments missing or too long')
    if _CONTROL.search(raw_args):
        raise ArgumentRenderRefused('Arguments contain control characters')
    if len(body) > MAX_TEMPLATE_CHARS:
        raise ArgumentRenderRefused('Template too large')
    scan = scan_placeholders(body, names)
    if scan['ambiguous']:
        raise ArgumentRenderRefused('Template uses undocumented placeholder forms: ' + ', '.join(scan['ambiguous']))
    needs_argv = bool(scan['indexed'] or scan['named'])
    argv = split_arguments(raw_args) if needs_argv else None
    state = {'received': False}

    def sub(m):
        bs = m.group('bs')
        token = m.group(0)[len(bs):]
        if len(bs) == 1:
            # Documented escape: a single backslash makes the token literal.
            # Backslash removal is inferred from "A backslash before any other
            # `$` is left unchanged" (reported as an assumption).
            return token
        if m.group('all'):
            state['received'] = True
            return bs + raw_args
        if m.group('aidx') is not None or m.group('idx') is not None:
            idx = int(m.group('aidx') if m.group('aidx') is not None else m.group('idx'))
            if idx < len(argv):
                state['received'] = True
                return bs + argv[idx]
            return m.group(0)  # documented: missing index stays unchanged
        name = m.group('named')
        state['received'] = True  # documented: named counts even when empty
        pos = names.index(name)
        return bs + (argv[pos] if pos < len(argv) else '')

    text = _placeholder_regex(names).sub(sub, body)
    appended = False
    if raw_args != '' and not state['received']:
        text = text + APPEND_SEPARATOR + 'ARGUMENTS: ' + raw_args
        appended = True
    return {'text': text, 'received': state['received'], 'appended': appended, 'argv': argv}
