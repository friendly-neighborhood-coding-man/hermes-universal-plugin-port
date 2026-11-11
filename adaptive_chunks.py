"""Structure-aware, resumable, bounded LLM edit plans for long Markdown commands.

Foreign input is *never executed*. Each replacement must match an exact and unique
source span. The original document survives until ALL chunks return valid results.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CHUNK_LIMIT_SIMPLE = 8000
CHUNK_LIMIT_NORMAL = 6200
CHUNK_LIMIT_COMPLEX = 4300
MAX_CHUNKS = 22
MAX_EDITS_PER_CHUNK = 6
MAX_EDIT_OLD_CHARS = 420
MAX_EDIT_NEW_CHARS = 700

PATCH_SCHEMA = {
    'type': 'object',
    'properties': {
        'edits': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {'old': {'type': 'string'}, 'new': {'type': 'string'}},
                'required': ['old', 'new'], 'additionalProperties': False,
            },
        },
        'limitations': {'type': 'array', 'items': {'type': 'string'}},
        'requires_manual_review': {'type': 'boolean'},
    },
    'required': ['edits', 'limitations', 'requires_manual_review'],
    'additionalProperties': False,
}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def choose_limit(markdown: str) -> int:
    """Smaller logical units for host orchestration / multi-step workflows."""
    score = sum(markdown.count(s) for s in (
        'subagent_type', 'AskUserQuestion', 'PHASE CHECKPOINT', 'Task:',
        'EnterPlanMode', 'hooks:',
    ))
    if score >= 4:
        return CHUNK_LIMIT_COMPLEX
    if score:
        return CHUNK_LIMIT_NORMAL
    return CHUNK_LIMIT_SIMPLE


def split_markdown(markdown: str, *, limit: int | None = None) -> list[str]:
    """Preserve every byte of source text; never cut within a fenced code block.

    Prefer heading and paragraph boundaries, falling back to line boundaries for
    oversized paragraphs. A single oversized line or code fence is review-required.
    """
    limit = limit or choose_limit(markdown)
    if limit < 64:
        raise ValueError('Chunk limit too small')
    lines = markdown.splitlines(keepends=True)
    atoms: list[tuple[str, bool, bool]] = []  # text, is_heading, is_fence
    accum = []
    fence = None
    def flush(is_fence=False):
        if accum:
            value = ''.join(accum)
            atoms.append((value, bool(re.match(r'^\s{0,3}#{1,6}\s', value)), is_fence))
            accum.clear()
    for line in lines:
        fence_match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if fence is None and fence_match:
            flush()
            fence = (fence_match.group(1)[0], len(fence_match.group(1)))
            accum.append(line)
            continue
        if fence is not None:
            accum.append(line)
            if re.match(r'^\s{0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}\s*$', line):
                flush(is_fence=True)
                fence = None
            continue
        if re.match(r'^\s{0,3}#{1,6}\s', line):
            flush()
            accum.append(line)
            flush()
        elif line.strip() == '':
            accum.append(line)
            flush()
        else:
            accum.append(line)
    if fence is not None:
        raise ValueError('Unclosed Markdown code fence')
    flush()
    expanded: list[tuple[str, bool]] = []
    for block, heading, is_fence in atoms:
        if len(block) <= limit:
            expanded.append((block, heading))
        elif is_fence:
            raise ValueError('Code fence exceeds bounded model context')
        else:
            partial = ''
            for line in block.splitlines(keepends=True):
                if len(line) > limit:
                    raise ValueError('Single Markdown line exceeds bounded model context')
                if partial and len(partial) + len(line) > limit:
                    expanded.append((partial, False))
                    partial = ''
                partial += line
            if partial:
                expanded.append((partial, False))
    chunks = []
    current = ''
    for block, heading in expanded:
        # Heading-aware split: keep smaller sections together where possible.
        if current and (len(current) + len(block) > limit or (heading and len(current) > limit // 2)):
            chunks.append(current)
            current = ''
        current += block
    if current:
        chunks.append(current)
    if ''.join(chunks) != markdown:
        raise AssertionError('Structure-aware chunking dropped source bytes')
    if len(chunks) > MAX_CHUNKS:
        raise ValueError('Command requires too many chunks for bounded processing')
    return chunks


def validate_edits(chunk: str, value: object) -> tuple[str, list[str], bool, list[dict]]:
    """Return patched text or raise ValueError; never execute model-produced text."""
    if not isinstance(value, dict):
        raise ValueError('Patch output is not an object')
    edits, limits, review = (value.get('edits'), value.get('limitations'), value.get('requires_manual_review'))
    if (not isinstance(edits, list) or len(edits) > MAX_EDITS_PER_CHUNK
            or not isinstance(limits, list) or not all(isinstance(x, str) for x in limits)
            or type(review) is not bool):
        raise ValueError('Patch output has invalid fields')
    ranges = []
    accepted = []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'old', 'new'}:
            raise ValueError('Invalid edit object')
        old, new = edit['old'], edit['new']
        if (not isinstance(old, str) or not isinstance(new, str) or not old
                or len(old) > MAX_EDIT_OLD_CHARS or len(new) > MAX_EDIT_NEW_CHARS):
            raise ValueError('Oversized or malformed edit')
        if chunk.count(old) != 1:
            raise ValueError('Edit does not uniquely match this chunk')
        start = chunk.index(old)
        end = start + len(old)
        if any(start < hi and lo < end for lo, hi, _ in ranges):
            raise ValueError('Overlapping patches')
        ranges.append((start, end, new))
        accepted.append({'old': old, 'new': new})
    output = chunk
    for start, end, new in sorted(ranges, reverse=True):
        output = output[:start] + new + output[end:]
    if len(output) > len(chunk) + 1500:
        raise ValueError('Patch expansion exceeded bound')
    # Editing the instruction text is not proof of equivalent execution, even
    # where the model reported zero limitations.
    return output, [s[:250] for s in limits[:12]], bool(review or edits), accepted


def read_progress(path: Path, source: str) -> dict:
    if not path.exists():
        return {'source_sha256': digest(source), 'pieces': {}}
    saved = json.loads(path.read_text(encoding='utf-8'))
    if saved.get('source_sha256') != digest(source):
        raise ValueError('Chunk source checksum differs from saved progress')
    if not isinstance(saved.get('pieces'), dict):
        raise ValueError('Invalid chunk progress')
    return saved
