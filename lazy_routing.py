"""P6.11 / P6.12 domain default routing + digest-validated lazy Skill loading.

route()      maps each step's domain to the operator's stored P6 domain default
             (uvp-data/p6-domain-defaults.json, read-only here). A domain with
             no stored default is NOT silently filled: the step returns
             NO_DEFAULT unless the caller passes an explicit, labelled mapping
             (for example the P6 recipe's fixed three Skills).
LazyLoader   loads a Skill body on first use per SESSION, keyed by (session, name)
             and bound to the body SHA-256 plus an optional cheap fingerprint.
             It revalidates on change, drops entries for missing Skills and refuses
             load or reuse when contract verification fails.
measure()    compares context size for the same task under eager stacking,
             per-step re-injection and lazy loading. Sizes are exact characters;
             the token figure is an APPROXIMATION (chars / 4), not billed tokens,
             and no cost saving is claimed from it.
"""
from __future__ import annotations

import hashlib
import json

if __package__:
    from .port_core import PortError
else:
    from port_core import PortError

APPROX_CHARS_PER_TOKEN = 4


def route(steps: list, stored_defaults: dict, *, explicit: dict | None = None) -> list:
    """steps: [{'id', 'domain'}]; stored_defaults: {domain: qualified_skill}."""
    out = []
    for s in steps:
        d = s["domain"]
        if d in stored_defaults:
            out.append({**s, "skill": stored_defaults[d], "source": "STORED_DOMAIN_DEFAULT"})
        elif explicit and d in explicit:
            out.append({**s, "skill": explicit[d], "source": "EXPLICIT_CALLER_MAPPING"})
        else:
            out.append({**s, "skill": None, "source": "NO_DEFAULT",
                        "action": "ask the user or run /uvp --p6-defaults; nothing is chosen silently"})
    return out


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LazyLoader:
    """Session-scoped, digest-validated lazy loading.

    - Reuse only when the cheap fingerprint from `stat(name)` (e.g. path, mtime_ns,
      size) is unchanged. Without `stat`, every reuse reloads and compares digests.
    - A changed fingerprint reloads: an identical digest is still reused (no
      re-injection); a different digest is injected again.
    - A missing or inaccessible Skill drops the cache entry and raises PortError.
    - `verify(name, body)` (for example the P6.8 contract installed SHA) must pass on
      every load and every validated reload; on failure nothing is loaded or reused.
    """

    def __init__(self, load_body, *, stat=None, verify=None):
        self._load, self._stat, self._verify = load_body, stat, verify
        self.cache: dict = {}
        self.loads = 0
        self.reuses = 0
        self.validated_reloads = 0
        self.reinjections = 0

    def _fetch(self, name):
        try:
            body = self._load(name)
        except Exception as exc:
            raise PortError("Skill %s inaccessible: %s" % (name, type(exc).__name__)) from exc
        if not isinstance(body, str):
            raise PortError("Skill %s returned no text" % name)
        if self._verify is not None and not self._verify(name, body):
            raise PortError("Skill %s failed contract verification; not loaded or reused" % name)
        return body

    def _fingerprint(self, name):
        if self._stat is None:
            return None
        try:
            return self._stat(name)
        except Exception as exc:
            raise PortError("Skill %s inaccessible: %s" % (name, type(exc).__name__)) from exc

    def get(self, name: str, session: str = "default") -> dict:
        key = (session, name)
        entry = self.cache.get(key)
        if entry is None:
            body = self._fetch(name)
            fp = self._fingerprint(name)
            self.loads += 1
            self.cache[key] = {"sha": _sha(body), "fp": fp}
            return {"name": name, "loaded": True, "changed": False, "text": body}
        try:
            fp = self._fingerprint(name)
            if fp is not None and fp == entry["fp"]:
                self.reuses += 1
                return self._ref(name, entry["sha"])
            body = self._fetch(name)
        except PortError:
            self.cache.pop(key, None)
            raise
        self.validated_reloads += 1
        sha = _sha(body)
        if sha == entry["sha"]:
            entry["fp"] = fp
            self.reuses += 1
            return self._ref(name, sha)
        self.cache[key] = {"sha": sha, "fp": fp}
        self.reinjections += 1
        return {"name": name, "loaded": True, "changed": True, "text": body}

    @staticmethod
    def _ref(name, sha):
        return {"name": name, "loaded": False, "changed": False,
                "text": "[Skill %s already loaded in this session (sha256 %s); follow it from above.]" % (name, sha[:16])}


def measure(plan: list, *, eager_message: str, per_step_message, lazy_body, stat=None) -> dict:
    """plan: routed steps. eager_message: one stacked message for all distinct Skills.
    per_step_message(name) -> the message a per-step slash invocation injects.
    lazy_body(name) -> what a lazy skill_view returns."""
    names = [p["skill"] for p in plan if p["skill"]]
    per_step = [per_step_message(n) for n in names]
    loader = LazyLoader(lazy_body, stat=stat)
    lazy = [loader.get(n)["text"] for n in names]

    def size(texts):
        chars = sum(len(t) for t in texts)
        return {"messages": len(texts), "chars": chars, "approx_tokens": chars // APPROX_CHARS_PER_TOKEN}

    return {"steps": len(plan), "distinct_skills": len(set(names)),
            "eager_stacked": size([eager_message]),
            "per_step_reinjection": size(per_step),
            "lazy_once": {**size(lazy), "skill_loads": loader.loads, "reuses": loader.reuses,
                          "validated_reloads": loader.validated_reloads, "reinjections": loader.reinjections},
            "tokenizer": "NOT_AVAILABLE_OFFLINE (no local Claude tokenizer; chars/4 is an approximation only)",
            "token_note": "approx_tokens = chars/%d; an approximation, not billed tokens" % APPROX_CHARS_PER_TOKEN,
            "cost_claim": "NONE (no billed-token measurement)"}


def read_stored_defaults(path) -> dict:
    """Read-only view of the P6 defaults file; missing file -> no defaults."""
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except FileNotFoundError:
        return {}
    return dict(data.get("domains") or {})
