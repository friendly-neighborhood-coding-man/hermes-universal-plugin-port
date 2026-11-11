"""P6 deterministic compatibility mapping engine with a bounded AI fallback.

Order of work for one foreign Skill:
  1. verified composition rules (largest spans first),
  2. verified 1:1 rules,
  3. residual extraction for everything left (exact span, context, attempted
     rule IDs, failure reason),
  4. only then, and only with explicit operator approval, the existing
     single-delta AI pipeline (`uvp_p6_patch.propose`) for residual kinds it
     is bounded to. Its output stays an immutable review candidate.

Rules live in the declarative, versioned registry `compat_rules.json`. The
registry can only *select* matcher/delta kinds implemented here; it cannot
carry code, regexes, permissions, network access or side effects. A rule may
be auto-applied only when its status is DIRECT_EXACT or COMPOSED_VERIFIED and
all of its validation cases resolve to PASS records in hash-pinned evidence
files. PROVISIONAL rules never change bytes; a match produces HOLD.

Three verification axes are kept apart and never merged into one percentage:
structural (bytes/syntax), runtime (target behavior) and semantic (same model
outcome). Nothing in this module calls a model, executes foreign content,
installs, enables or writes inside a staged plugin.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

if __package__:
    from .claude_command import (
        CommandFormatError, HERMES_INLINE_SHELL, KNOWN_FRONTMATTER, SEMANTICS_VERSION,
        _SHELL_FENCE_OPEN, declared_argument_names, parse_frontmatter, scan_placeholders,
    )
    from .port_core import PortError
else:  # script / CLI use from the checkout root
    from claude_command import (
        CommandFormatError, HERMES_INLINE_SHELL, KNOWN_FRONTMATTER, SEMANTICS_VERSION,
        _SHELL_FENCE_OPEN, declared_argument_names, parse_frontmatter, scan_placeholders,
    )
    from port_core import PortError

ENGINE_VERSION = "uvp-compat-engine/2026-11-11.1"
REGISTRY_SCHEMA = "universal-port.compat-rules/1"
REPORT_SCHEMA = "universal-port.compat-report/1"
LEDGER_SCHEMA = "universal-port.p6-candidate-ledger/1"
HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "compat_rules.json"
DEFAULT_LEDGER = HERE / "p6_candidate_ledger.json"

AUTO_STATUSES = frozenset({"DIRECT_EXACT", "COMPOSED_VERIFIED"})
STATUSES = AUTO_STATUSES | {"PROVISIONAL"}
AXES = {
    "structural": {"VERIFIED", "NOT_VERIFIED"},
    "runtime": {"VERIFIED", "TARGET_FUNCTIONS_PROBED", "NOT_VERIFIED"},
    "semantic": {"VERIFIED", "INPUT_TEXT_IDENTICAL", "NOT_ESTABLISHED"},
}
# match kind -> (rule kind, delta kind). Registry entries must use one of these pairs.
MATCHERS = {
    "usage_example_slash_all_arguments": ("composition", "rewrite_usage_line_to_hermes_plugin_slash"),
    "markdown_literal_region": ("direct", "identity"),
    "claude_skill_dir_variable": ("direct", "none_provisional"),
    "claude_skill_definition": ("direct", "none_verify_only"),
}
ALREADY_MAPPED_KINDS = {"usage_example_hermes_plugin_slash", None}
PRECONDITIONS = frozenset({
    "single_all_arguments_placeholder_in_file", "no_indexed_or_named_placeholders",
    "no_arguments_frontmatter", "placeholder_inside_usage_fence", "usage_line_names_this_skill",
    "argument_hint_single_line", "static_namespaced_registration_present",
    "no_host_tokens_in_region", "hermes_inline_shell_disabled", "source_semantics_pinned",
})
RULE_KEYS = {"id", "version", "kind", "status", "priority", "source", "target", "match",
             "contracts", "preconditions", "permissions", "side_effects", "graph", "delta",
             "validation", "axes", "provenance"}
NO_PERMISSIONS = {"adds": [], "network": False, "execution": False, "authorization": []}
MAX_RULES = 64
_ID = re.compile(r"^R-[CD]\d{3}$")
_CAP = re.compile(r"^(claude|hermes)\.[a-z_]+(?:\.[a-z_]+)?$")
_SHA = re.compile(r"^[0-9a-f]{64}$")

# --- construct scanners (shared by the matcher and post-proposal checks) ----
_CLAUDE_VAR = re.compile(r"\$\{(CLAUDE_[A-Z0-9_]+)\}")
_HERMES_VAR = re.compile(r"\$\{(HERMES_SKILL_DIR|HERMES_SESSION_ID)\}")
_CONNECTOR = re.compile(r"~~([A-Za-z][A-Za-z0-9 -]{0,40}?)(?=\*\*|[`),.:;]|\s*$)")
_LINK = re.compile(r"\[([^\]\n]*)\]\(([^)\s]+)\)")
_SLASH = re.compile(r"^/([A-Za-z][\w.-]*(?::[\w.-]+)?)(?:[ \t]+(.*))?$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_TOOL_LINE = re.compile(r"^\s{0,3}Tool:\s*\S+", re.I)
_UNSAFE_NEW = re.compile(
    r"(?i)(https?://|curl\b|wget\b|powershell\b|bash\s+-c\b|subprocess\b|"
    r"api[_-]?key\b|password\b|token\b|!`|mcp__|allowed-tools)")


class CompatRegistryError(PortError):
    """The registry or its evidence is not trustworthy; nothing may be mapped."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canon(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


# --- registry --------------------------------------------------------------

def _read_pinned(base: Path, rel: str, expected: str) -> bytes:
    if not isinstance(rel, str) or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        raise CompatRegistryError("Evidence path must be relative and contained")
    p = base / rel
    if p.is_symlink() or not p.is_file():
        raise CompatRegistryError("Evidence file missing or linked: " + rel)
    raw = p.read_bytes()
    if not isinstance(expected, str) or not _SHA.fullmatch(expected) or sha256(raw) != expected:
        raise CompatRegistryError("Evidence hash mismatch: " + rel)
    return raw


def _validate_graph(rule: dict) -> list[str]:
    """Validate a bounded composition graph; return a deterministic node order."""
    g = rule["graph"]
    if not isinstance(g, dict) or set(g) != {"inputs", "nodes", "bindings", "outputs"}:
        raise CompatRegistryError(rule["id"] + ": malformed composition graph")
    nodes = g["nodes"]
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 8:
        raise CompatRegistryError(rule["id"] + ": composition must have 2..8 nodes")
    by_id = {}
    for n in nodes:
        if (not isinstance(n, dict) or set(n) != {"id", "side", "capability", "inputs", "outputs"}
                or n["side"] not in {"source", "target"} or n["id"] in by_id):
            raise CompatRegistryError(rule["id"] + ": malformed or duplicate graph node")
        by_id[n["id"]] = n
    for side in ("source", "target"):
        caps = [n["capability"] for n in nodes if n["side"] == side]
        if sorted(caps) != sorted(rule[side]["capabilities"]) or len(set(caps)) != len(caps):
            raise CompatRegistryError(rule["id"] + ": graph capabilities differ from declared " + side)
    ext = set(g["inputs"])
    bound, edges = {}, {k: set() for k in by_id}
    for b in g["bindings"]:
        if not isinstance(b, dict) or set(b) != {"to", "from"}:
            raise CompatRegistryError(rule["id"] + ": malformed binding")
        to_node, _, to_port = b["to"].partition(".")
        if to_node not in by_id or to_port not in by_id[to_node]["inputs"]:
            raise CompatRegistryError(rule["id"] + ": binding to unknown input " + b["to"])
        if b["to"] in bound:
            raise CompatRegistryError(rule["id"] + ": input bound twice " + b["to"])
        src_node, _, src_port = b["from"].partition(".")
        if src_node == "$input":
            if src_port not in ext:
                raise CompatRegistryError(rule["id"] + ": unknown external input " + b["from"])
        else:
            if src_node not in by_id or src_port not in by_id[src_node]["outputs"]:
                raise CompatRegistryError(rule["id"] + ": binding from unknown output " + b["from"])
            if by_id[src_node]["side"] != by_id[to_node]["side"]:
                raise CompatRegistryError(rule["id"] + ": source/target subgraphs may not exchange data")
            edges[src_node].add(to_node)
        bound[b["to"]] = b["from"]
    for n in nodes:
        for port in n["inputs"]:
            if n["id"] + "." + port not in bound:
                raise CompatRegistryError(rule["id"] + ": missing input binding " + n["id"] + "." + port)
    # Kahn topological sort with lexical tie-break: deterministic, rejects cycles.
    indeg = {k: 0 for k in by_id}
    for k, outs in edges.items():
        for o in outs:
            indeg[o] += 1
    ready = sorted(k for k, d in indeg.items() if d == 0)
    order = []
    while ready:
        k = ready.pop(0)
        order.append(k)
        for o in sorted(edges[k]):
            indeg[o] -= 1
            if indeg[o] == 0:
                ready.append(o)
                ready.sort()
    if len(order) != len(by_id):
        raise CompatRegistryError(rule["id"] + ": composition graph has a cycle")
    outs = g["outputs"]
    if not isinstance(outs, dict) or set(outs) != {"source", "target"}:
        raise CompatRegistryError(rule["id"] + ": composition must name one source and one target output")
    for side, ref in outs.items():
        node, _, port = str(ref).partition(".")
        if node not in by_id or by_id[node]["side"] != side or port not in by_id[node]["outputs"]:
            raise CompatRegistryError(rule["id"] + ": bad composition output " + str(ref))
    # Both sides must consume the same external inputs (same data enters each).
    used = {side: {f.partition(".")[2] for t, f in bound.items()
                   if f.startswith("$input.") and by_id[t.partition(".")[0]]["side"] == side}
            for side in ("source", "target")}
    if used["source"] != used["target"] or used["source"] != ext:
        raise CompatRegistryError(rule["id"] + ": source and target consume different external inputs")
    return order


def _validate_rule(rule, probe_cases: dict, claude_cases: set) -> dict:
    if not isinstance(rule, dict) or set(rule) != RULE_KEYS:
        raise CompatRegistryError("Rule fields malformed")
    rid = rule["id"]
    if not isinstance(rid, str) or not _ID.fullmatch(rid):
        raise CompatRegistryError("Bad rule id")
    if not isinstance(rule["version"], int) or rule["version"] < 1:
        raise CompatRegistryError(rid + ": version must be a positive integer")
    if rule["status"] not in STATUSES or rule["kind"] not in {"direct", "composition"}:
        raise CompatRegistryError(rid + ": unknown status or kind")
    if not isinstance(rule["priority"], int) or not 0 <= rule["priority"] <= 999:
        raise CompatRegistryError(rid + ": bad priority")
    for side, host in (("source", "claude-code"), ("target", "hermes")):
        s = rule[side]
        if (not isinstance(s, dict) or set(s) != {"host", "version", "capabilities"} or s["host"] != host
                or not isinstance(s["version"], str) or not s["version"].strip()
                or not isinstance(s["capabilities"], list) or not s["capabilities"]
                or not all(isinstance(c, str) and _CAP.fullmatch(c) and c.startswith(host.split("-")[0] + ".")
                           for c in s["capabilities"])):
            raise CompatRegistryError(rid + ": bad " + side + " host/version/capabilities")
    m = rule["match"]
    if (not isinstance(m, dict) or set(m) != {"kind", "already_mapped_kind"}
            or m["kind"] not in MATCHERS or m["already_mapped_kind"] not in ALREADY_MAPPED_KINDS):
        raise CompatRegistryError(rid + ": unimplemented matcher")
    want_kind, want_delta = MATCHERS[m["kind"]]
    if rule["kind"] != want_kind or rule["delta"] != {"kind": want_delta}:
        raise CompatRegistryError(rid + ": matcher/delta/kind pairing not implemented")
    if (not isinstance(rule["contracts"], dict) or set(rule["contracts"]) != {"input", "output"}
            or not all(isinstance(v, str) and v.strip() for v in rule["contracts"].values())):
        raise CompatRegistryError(rid + ": input/output contract required")
    pre = rule["preconditions"]
    if not isinstance(pre, list) or not pre or not set(pre) <= PRECONDITIONS or len(set(pre)) != len(pre):
        raise CompatRegistryError(rid + ": unknown or empty preconditions")
    # No rule may carry permission, network, execution or authorization growth.
    if rule["permissions"] != NO_PERMISSIONS or rule["side_effects"] != []:
        raise CompatRegistryError(rid + ": rules may not add permissions, network, execution, authorization or side effects")
    if not isinstance(rule["axes"], dict) or set(rule["axes"]) != set(AXES) or any(
            rule["axes"][k] not in AXES[k] for k in AXES):
        raise CompatRegistryError(rid + ": verification axes malformed")
    v = rule["validation"]
    if (not isinstance(v, dict) or set(v) != {"source_cases", "target_cases"}
            or not isinstance(v["source_cases"], list) or not isinstance(v["target_cases"], list)):
        raise CompatRegistryError(rid + ": validation evidence malformed")
    for c in v["target_cases"]:
        if c not in probe_cases:
            raise CompatRegistryError(rid + ": unknown target evidence case " + str(c))
    for c in v["source_cases"]:
        if c not in claude_cases:
            raise CompatRegistryError(rid + ": unknown source evidence case " + str(c))
    p = rule["provenance"]
    if not isinstance(p, dict) or not {"author", "created", "basis", "limitation"} <= set(p):
        raise CompatRegistryError(rid + ": provenance required")
    order = None
    if rule["kind"] == "composition":
        if len(rule["source"]["capabilities"]) + len(rule["target"]["capabilities"]) < 3:
            raise CompatRegistryError(rid + ": composition needs N:1, 1:N or N:M capabilities")
        order = _validate_graph(rule)
    elif rule["graph"] is not None or len(rule["source"]["capabilities"]) != 1 or len(rule["target"]["capabilities"]) != 1:
        raise CompatRegistryError(rid + ": a direct rule is exactly 1:1 with no graph")
    if rule["status"] in AUTO_STATUSES:
        if rule["status"] == "DIRECT_EXACT" and rule["kind"] != "direct":
            raise CompatRegistryError(rid + ": DIRECT_EXACT is only for 1:1 rules")
        if rule["status"] == "COMPOSED_VERIFIED" and rule["kind"] != "composition":
            raise CompatRegistryError(rid + ": COMPOSED_VERIFIED is only for compositions")
        cases = [probe_cases[c] for c in v["target_cases"]]
        if not v["source_cases"] or not cases or any(c["result"] != "PASS" for c in cases):
            raise CompatRegistryError(rid + ": auto-applied rule lacks PASS source and target evidence")
        if not any(c["kind"] == "behavioral" for c in cases):
            raise CompatRegistryError(rid + ": auto-applied rule needs behavioral target evidence, not only code review")
        if rule["axes"]["structural"] != "VERIFIED" or rule["axes"]["runtime"] == "NOT_VERIFIED":
            raise CompatRegistryError(rid + ": auto-applied rule must be structurally verified and runtime-probed")
    return {**rule, "_graph_order": order}


def load_registry(path: Path | None = None) -> dict:
    """Load and fully validate the declarative registry and its pinned evidence."""
    path = Path(path) if path is not None else DEFAULT_REGISTRY
    if path.is_symlink() or not path.is_file():
        raise CompatRegistryError("Compatibility registry missing or linked")
    raw = path.read_bytes()
    if len(raw) > 256_000:
        raise CompatRegistryError("Registry too large")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise CompatRegistryError("Registry is not JSON") from exc
    if (not isinstance(data, dict) or set(data) != {"schema", "registry_version", "evidence", "rules"}
            or data["schema"] != REGISTRY_SCHEMA or not isinstance(data["registry_version"], str)):
        raise CompatRegistryError("Unrecognized registry schema")
    base = path.resolve().parent
    ev = data["evidence"]
    if not isinstance(ev, dict) or set(ev) != {"hermes_target_probe", "claude_semantics"}:
        raise CompatRegistryError("Registry evidence block malformed")
    probe = json.loads(_read_pinned(base, ev["hermes_target_probe"].get("path"), ev["hermes_target_probe"].get("sha256")))
    if probe.get("schema") != "universal-port.hermes-target-probe/1" or probe.get("model_calls") != 0:
        raise CompatRegistryError("Unrecognized target probe evidence")
    if probe.get("probed_files_dirty") is not False:
        raise CompatRegistryError("Target probe ran on modified Hermes source")
    probe_cases = {c["id"]: c for c in probe.get("cases", [])
                   if isinstance(c, dict) and c.get("kind") in {"behavioral", "source_assertion"}}
    cs = ev["claude_semantics"]
    if cs.get("semantics_version") != SEMANTICS_VERSION:
        raise CompatRegistryError("Claude semantics oracle version differs from claude_command.py")
    claude = json.loads(_read_pinned(base, cs.get("cases_path"), cs.get("cases_sha256")))
    if claude.get("source_sha256") != cs.get("source_doc_sha256"):
        raise CompatRegistryError("Claude case oracle is bound to a different source document")
    claude_cases = {c["id"] for c in claude.get("cases", []) if isinstance(c, dict)}
    rules = data["rules"]
    if not isinstance(rules, list) or not rules or len(rules) > MAX_RULES:
        raise CompatRegistryError("Registry rules malformed")
    out, ids, auto_kinds = [], set(), {}
    for r in rules:
        v = _validate_rule(r, probe_cases, claude_cases)
        if v["id"] in ids:
            raise CompatRegistryError("Duplicate rule id " + v["id"])
        ids.add(v["id"])
        key = v["match"]["kind"]
        if key in auto_kinds:
            # Unambiguous rule selection: one rule per construct kind.
            raise CompatRegistryError("Ambiguous rules for construct " + key + ": " + auto_kinds[key] + ", " + v["id"])
        auto_kinds[key] = v["id"]
        out.append(v)
    out.sort(key=lambda r: (r["priority"], r["id"]))
    return {"registry_version": data["registry_version"], "sha256": sha256(raw), "rules": out,
            "target_identity": probe.get("target_identity"),
            "probe_sha256": ev["hermes_target_probe"]["sha256"]}


def default_identity(registry: dict) -> dict:
    return {"source": SEMANTICS_VERSION, "target": registry["target_identity"]}


# --- stage inspection (static, read-only) ----------------------------------

def stage_catalog(root: Path) -> dict:
    """Static namespaced registration read from a generated stage, never imported."""
    yaml = root / "plugin.yaml"
    init = root / "__init__.py"
    if yaml.is_symlink() or init.is_symlink() or not yaml.is_file() or not init.is_file():
        raise PortError("Stage manifest or registration entry missing")
    names = [ln.split(":", 1)[1].strip() for ln in yaml.read_text(encoding="utf-8").splitlines()
             if ln.startswith("name:")]
    if len(names) != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", names[0]):
        raise PortError("Stage plugin name unreadable")
    tree = ast.parse(init.read_bytes())
    skills = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_SKILLS" for t in node.targets):
            skills = ast.literal_eval(node.value)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "register_skill"]
    if not isinstance(skills, tuple) or not all(isinstance(s, str) for s in skills) or len(calls) != 1:
        raise PortError("Stage registration is not the static generated form")
    ns = names[0]
    return {"namespace": ns, "skills": list(skills), "source": "STATIC_INIT_PY",
            "slash_keys": sorted("/" + (ns + ":" + s).lower() for s in skills),
            "qualified": sorted(ns + ":" + s for s in skills)}


def checked_stage(stage: str) -> tuple[Path, dict]:
    p = Path(stage).expanduser()
    if p.is_symlink() or not p.is_dir():
        raise PortError("Missing or linked stage")
    root = p.resolve()
    rep = root / "PORTING_REPORT.json"
    if rep.is_symlink() or not rep.is_file():
        raise PortError("Missing P6 stage identity")
    report = json.loads(rep.read_text(encoding="utf-8"))
    if report.get("schema") != "universal-port.p6-stage/1" or report.get("installation_performed") is not False:
        raise PortError("Invalid staged P6 bundle")
    return root, report


# --- per-line scanning -----------------------------------------------------

def _line_info(lines: list[str], body_start: int) -> list[dict]:
    info, fence, section = [], None, ""
    for i, raw in enumerate(lines):
        line = raw.rstrip("\r\n")
        entry = {"in_fence": False, "fence_marker": False, "section": section}
        if i < body_start:
            entry["frontmatter"] = True
            info.append(entry)
            continue
        entry["frontmatter"] = False
        mk = _FENCE.match(line)
        if mk:
            chars = mk.group(1)
            if fence is None:
                fence = (chars[0], len(chars))
            elif chars[0] == fence[0] and len(chars) >= fence[1] and not line.strip()[len(chars):].strip():
                fence = None
            entry["fence_marker"] = True
        elif fence is not None:
            entry["in_fence"] = True
        else:
            h = _HEADING.match(line)
            if h:
                section = h.group(2).strip()
                entry["section"] = section
        info.append(entry)
    return info


def _tokens(line: str, names: list[str]) -> dict:
    ph = scan_placeholders(line, names)
    return {
        "placeholders": ph["all"] + ph["indexed"] + ph["named"] + ph["escaped"] + len(ph["ambiguous"]),
        "claude_vars": _CLAUDE_VAR.findall(line),
        "hermes_vars": _HERMES_VAR.findall(line),
        "shell": bool(HERMES_INLINE_SHELL.search(line) or _SHELL_FENCE_OPEN.match(line)),
        "connectors": [c.strip() for c in _CONNECTOR.findall(line)],
        "links": [t for _, t in _LINK.findall(line)
                  if "://" not in t and not t.startswith(("#", "mailto:"))],
        "slash": _SLASH.match(line.strip()),
        "tool_line": bool(_TOOL_LINE.match(line)),
    }


def _resolve_resource(link: str, source_skill_dir: Path | None, source_root: Path | None,
                      target_skill_dir: Path | None, target_root: Path | None) -> dict:
    target = link.split("#", 1)[0]

    def inside(base, root):
        if base is None or root is None:
            return None
        p = (base / target).resolve()
        return bool(p.is_file() and p.is_relative_to(root.resolve()))

    in_source = inside(source_skill_dir, source_root)
    in_target = inside(target_skill_dir, target_root)
    loadable = (".." not in Path(target).parts) and bool(
        target_skill_dir is not None and (target_skill_dir / target).is_file())
    return {"link": link, "resolves_in_source_tree": in_source, "resolves_in_target_tree": in_target,
            "hermes_skill_view_file_path_loadable": loadable,
            "hermes_skill_view_rule": "skill_view(file_path=...) rejects any '..' component (probe H-SKILL-VIEW-TRAVERSAL-1)"}


def _span(lines, i, text):
    lo, hi = max(0, i - 2), min(len(lines), i + 3)
    return {"start_line": i + 1, "end_line": i + 1, "start_col": 1, "end_col": len(text) + 1,
            "text": text, "context": [ln.rstrip("\r\n") for ln in lines[lo:hi]], "context_start_line": lo + 1}


# --- the matcher / executor ------------------------------------------------

def map_skill_text(text: str, *, skill: str, catalog: dict, registry: dict, identity: dict,
                   source_skill_dir: Path | None = None, source_root: Path | None = None,
                   target_skill_dir: Path | None = None, target_root: Path | None = None) -> dict:
    """Deterministically map one Claude SKILL.md. Never calls a model."""
    rules = {r["match"]["kind"]: r for r in registry["rules"]}
    lines = text.splitlines(keepends=True)
    holds, residuals, unsupported, matches, deltas, provisional = [], [], [], [], [], []
    try:
        meta, body, unparsed = parse_frontmatter(text)
        names = declared_argument_names(meta)
    except CommandFormatError as exc:
        return {"skill": skill, "status": "HOLD", "holds": ["FRONTMATTER_UNPARSEABLE: " + str(exc)],
                "mapped_text": text, "changed": False, "model_calls": 0, "residuals": [], "matches": [],
                "deltas": [], "unsupported": [], "provisional": [], "constructs": {}}
    body_start = len(lines) - len(body.splitlines(keepends=True)) if body else len(lines)
    info = _line_info(lines, body_start)
    qualified = catalog["namespace"] + ":" + skill
    registered = qualified in catalog["qualified"]

    def version_ok(rule):
        return rule["source"]["version"] == identity.get("source") and rule["target"]["version"] == identity.get("target")

    def ref(rule):
        return {"rule_id": rule["id"], "rule_version": rule["version"], "status": rule["status"]}

    consumed: set[int] = set()
    constructs = {}

    # Skill definition (frontmatter) -> namespaced registration (R-D003, verify-only).
    r_def = rules.get("claude_skill_definition")
    fm_keys = sorted(meta)
    for k in fm_keys:
        mode = KNOWN_FRONTMATTER.get(k)
        if k == "name":
            continue
        if mode is None:
            unsupported.append({"kind": "frontmatter_key_unknown", "key": k, "classification": "NOT_PORTED"})
        elif mode.startswith("not_"):
            unsupported.append({"kind": "frontmatter_key_not_preservable", "key": k, "classification": mode})
    for k in unparsed:
        unsupported.append({"kind": "frontmatter_value_unparsed", "key": k, "classification": "NOT_PORTED"})
    constructs["skill_definition"] = {
        "file_lines": [1, body_start] if body_start else None, "frontmatter_keys": fm_keys,
        "declared_name": meta.get("name"), "description_present": bool(meta.get("description")),
        "argument_hint": meta.get("argument-hint"),
        "note": "Claude Skill definition. Not a Hermes registration by itself."}
    if r_def:
        ok = registered and meta.get("name") == skill and version_ok(r_def)
        provisional.append({**ref(r_def), "construct": "skill_definition", "preconditions_met": ok,
                            "effect": "verification only; no bytes changed"})
        if meta.get("name") != skill:
            holds.append("SKILL_NAME_MISMATCH")
    constructs["hermes_namespaced_registration"] = {
        "qualified_name": qualified, "registered_statically": registered, "evidence_source": catalog["source"],
        "runtime_catalog_checked": False,
        "note": "ctx.register_skill(name, path) in generated __init__.py; separate from the SKILL.md definition."}
    for i in range(body_start):
        consumed.add(i)

    # Composition rule R-C001: usage example + $ARGUMENTS -> Hermes plugin slash + instruction append.
    r_c = rules.get("usage_example_slash_all_arguments")
    scan = scan_placeholders(body, names)
    usage_idx = [i for i in range(body_start, len(lines))
                 if info[i]["in_fence"] and info[i]["section"].lower() == "usage"
                 and _SLASH.match(lines[i].strip())]
    usage_entries = []
    for i in usage_idx:
        m = _SLASH.match(lines[i].strip())
        usage_entries.append({"line": i + 1, "text": lines[i].rstrip("\r\n"), "command_token": m.group(1),
                              "argument_text": m.group(2), "in_fence": True, "section": "Usage",
                              "executed_by_either_host": False})
    constructs["markdown_usage_example"] = usage_entries or None
    if r_c:
        for i in usage_idx:
            m = _SLASH.match(lines[i].strip())
            token, rest = m.group(1), (m.group(2) or "").strip()
            if token.lower() == qualified.lower():
                consumed.add(i)
                matches.append({**ref(r_c), "kind": "composition", "line": i + 1, "outcome": "ALREADY_MAPPED"})
                continue
            if "$ARGUMENTS" not in lines[i]:
                continue
            hint = meta.get("argument-hint")
            pre = {
                "single_all_arguments_placeholder_in_file": scan["all"] == 1,
                "no_indexed_or_named_placeholders": scan["indexed"] == 0 and scan["named"] == 0 and not scan["ambiguous"] and scan["escaped"] == 0,
                "no_arguments_frontmatter": "arguments" not in meta,
                "placeholder_inside_usage_fence": True,
                "usage_line_names_this_skill": token == skill and rest == "$ARGUMENTS",
                "argument_hint_single_line": isinstance(hint, str) and bool(hint.strip()) and "\n" not in hint
                    and not any(_tokens(hint, names)[k] for k in ("placeholders", "claude_vars", "hermes_vars", "shell", "links")),
                "static_namespaced_registration_present": registered,
            }
            failed = sorted(k for k in r_c["preconditions"] if not pre.get(k, False))
            consumed.add(i)
            if not version_ok(r_c):
                failed = ["VERSION_MISMATCH"] + failed
            if failed:
                holds.append("R-C001 preconditions failed at line %d: %s" % (i + 1, ", ".join(failed)))
                residuals.append({"kind": "arguments_placeholder", "span": _span(lines, i, lines[i].rstrip("\r\n")),
                                  "attempted_rule_ids": [r_c["id"]], "reason": "PRECONDITION_OR_VERSION_FAILED: " + ", ".join(failed),
                                  "ai_eligible": "VERSION_MISMATCH" not in failed})
                continue
            raw = lines[i]
            ending = raw[len(raw.rstrip("\r\n")):]
            indent = raw[:len(raw) - len(raw.lstrip())]
            new_line = indent + "/" + qualified + " " + hint.strip() + ending
            lines[i] = new_line
            deltas.append({"rule_id": r_c["id"], "rule_version": r_c["version"], "line": i + 1,
                           "old": raw.rstrip("\r\n"), "new": new_line.rstrip("\r\n")})
            matches.append({**ref(r_c), "kind": "composition", "line": i + 1, "outcome": "APPLIED",
                            "source_capabilities": r_c["source"]["capabilities"],
                            "target_capabilities": r_c["target"]["capabilities"],
                            "graph_order": r_c["_graph_order"], "axes": r_c["axes"]})

    constructs["host_command_invocation"] = {
        "claude_form": "/" + skill + " <user_text>",
        "hermes_slash_form": "/" + qualified.lower() + " <user_text>",
        "hermes_slash_key_in_static_catalog": ("/" + qualified.lower()) in catalog["slash_keys"],
        "runtime_resolved": False,
        "note": "A runtime user action. The Usage line only depicts it; neither host executes the Usage block."}
    constructs["runtime_skill_view_resolution"] = {
        "call": 'skill_view("' + qualified + '")', "executed": False,
        "user_input_channel": "NONE: skill_view returns the body only; the user's task is in conversation context",
        "relative_file_loads": "skill_view(file_path=...) only inside the skill dir, no '..'"}
    constructs["user_input_passing"] = {
        "claude_slash": "user_text substituted at $ARGUMENTS (no ARGUMENTS: append because a placeholder received it)",
        "hermes_slash": "user_text appended after the body: 'The user has provided the following instruction alongside the skill invocation: <user_text>' (probe H-INSTRUCTION-APPEND-1)",
        "hermes_skill_view": "not passed by the call",
        "hermes_substitutes_ARGUMENTS": False,
        "mapping_rule": r_c["id"] if r_c else None}

    # Remaining body lines: residuals, unsupported, provisional, and literal passthrough.
    r_lit = rules.get("markdown_literal_region")
    r_dir = rules.get("claude_skill_dir_variable")
    literal_lines, resources = [], []
    for i in range(body_start, len(lines)):
        if i in consumed:
            continue
        line = lines[i].rstrip("\r\n")
        t = _tokens(line, names)
        is_residual = False
        if t["shell"]:
            residuals.append({"kind": "shell_injection", "span": _span(lines, i, line), "attempted_rule_ids": [],
                              "reason": "BLOCKED: shell injection is never mapped", "ai_eligible": False})
            is_residual = True
        if t["placeholders"]:
            residuals.append({"kind": "arguments_placeholder", "span": _span(lines, i, line),
                              "attempted_rule_ids": [r_c["id"]] if r_c else [],
                              "reason": "Placeholder outside a matching Usage example",
                              "ai_eligible": True})
            is_residual = True
        for var in t["claude_vars"]:
            if var == "CLAUDE_SKILL_DIR" and r_dir:
                residuals.append({"kind": "claude_host_variable", "span": _span(lines, i, line),
                                  "attempted_rule_ids": [r_dir["id"]],
                                  "reason": "RULE_PROVISIONAL: " + r_dir["id"] + " is not verified", "ai_eligible": False})
                holds.append("Provisional rule %s matched at line %d" % (r_dir["id"], i + 1))
            else:
                residuals.append({"kind": "claude_host_variable", "span": _span(lines, i, line), "attempted_rule_ids": [],
                                  "reason": "NO_RULE for ${" + var + "}", "ai_eligible": False})
            is_residual = True
        if t["hermes_vars"]:
            residuals.append({"kind": "target_token_collision", "span": _span(lines, i, line), "attempted_rule_ids": [],
                              "reason": "Literal ${HERMES_*} would be rewritten by Hermes but not by Claude",
                              "ai_eligible": False})
            is_residual = True
        if t["slash"] and not (t["slash"].group(1).lower() == qualified.lower()):
            residuals.append({"kind": "host_command_reference", "span": _span(lines, i, line),
                              "attempted_rule_ids": [r_c["id"]] if r_c else [],
                              "reason": "Slash command '/" + t["slash"].group(1) + "' is not in the Hermes catalog for this plugin",
                              "ai_eligible": False})
            is_residual = True
        if t["tool_line"]:
            residuals.append({"kind": "unmapped_tool_call", "span": _span(lines, i, line), "attempted_rule_ids": [],
                              "reason": "verified_mappings.json has no verified tool alias", "ai_eligible": False})
            is_residual = True
        for link in t["links"]:
            res = _resolve_resource(link, source_skill_dir, source_root, target_skill_dir, target_root)
            res["line"] = i + 1
            resources.append(res)
            if res["resolves_in_target_tree"] is not True:
                residuals.append({"kind": "unresolved_resource", "span": _span(lines, i, line), "attempted_rule_ids": [],
                                  "reason": "Relative resource '%s' does not resolve in the active target tree" % link,
                                  "ai_eligible": False, "resource": res})
                is_residual = True
        for cat in t["connectors"]:
            unsupported.append({"kind": "connector_placeholder", "category": cat, "line": i + 1,
                                "classification": "SKILLS_ONLY_PARTIAL",
                                "note": "Claude MCP/OAuth connector category; not connected, not emulated"})
        if not is_residual and not t["connectors"] and not t["links"]:
            literal_lines.append(i)
    regions = []
    for i in literal_lines:
        if regions and regions[-1][1] == i - 1:
            regions[-1][1] = i
        else:
            regions.append([i, i])
    if r_lit:
        if version_ok(r_lit):
            for a, b in regions:
                matches.append({**ref(r_lit), "kind": "direct", "lines": [a + 1, b + 1], "outcome": "IDENTITY"})
        else:
            holds.append("R-D001 VERSION_MISMATCH")

    # Defensive ambiguity check: no two matches may claim the same line.
    claimed = {}
    for m in matches:
        span = range(m["lines"][0], m["lines"][1] + 1) if "lines" in m else [m["line"]]
        for ln in span:
            if ln in claimed:
                raise PortError("Ambiguous overlapping rule matches at line %d" % ln)
            claimed[ln] = m["rule_id"]

    mapped = "".join(lines)
    status = "HOLD" if holds else ("DETERMINISTIC_PARTIAL" if residuals or unsupported else "DETERMINISTIC_COMPLETE")
    return {"skill": skill, "status": status, "holds": holds, "matches": matches, "deltas": deltas,
            "residuals": residuals, "unsupported": unsupported, "provisional": provisional,
            "resources": resources, "constructs": constructs, "mapped_text": mapped,
            "changed": mapped != text, "model_calls": 0}


def _axes_for(result: dict) -> dict:
    gaps = sorted({r["kind"] for r in result["residuals"]} | ({"hold"} if result["holds"] else set()))
    return {"structural": "NOT_VERIFIED" if gaps else "VERIFIED", "structural_gaps": gaps,
            "runtime": "NOT_VERIFIED (no Hermes session; target functions probed offline only)",
            "semantic": "NOT_ESTABLISHED"}


# --- post-proposal checks (AI or any other candidate) ---------------------

def check_candidate(original: str, candidate: str, *, skill: str, catalog: dict,
                    source_skill_dir: Path | None = None, source_root: Path | None = None,
                    target_skill_dir: Path | None = None, target_root: Path | None = None) -> dict:
    """Independent checks on a proposed Skill body. Never calls a model."""
    qualified = catalog["namespace"] + ":" + skill
    keys = set(catalog["slash_keys"])

    def facts(text):
        try:
            meta, body, _ = parse_frontmatter(text)
            names = declared_argument_names(meta)
        except CommandFormatError:
            return None
        lines = text.splitlines(keepends=True)
        start = len(lines) - len(body.splitlines(keepends=True)) if body else len(lines)
        f = {"placeholders": 0, "shell": 0, "claude_vars": set(), "slash_unresolved": set(),
             "connectors": set(), "links_unresolved": set(), "unsafe": set(), "tool_lines": 0,
             "frontmatter": "".join(lines[:start])}
        for i in range(start, len(lines)):
            line = lines[i].rstrip("\r\n")
            t = _tokens(line, names)
            f["placeholders"] += t["placeholders"]
            f["shell"] += int(t["shell"])
            f["claude_vars"].update(t["claude_vars"])
            f["tool_lines"] += int(t["tool_line"])
            if t["slash"] and ("/" + t["slash"].group(1).lower()) not in keys:
                f["slash_unresolved"].add("/" + t["slash"].group(1))
            f["connectors"].update(t["connectors"])
            for link in t["links"]:
                if _resolve_resource(link, source_skill_dir, source_root, target_skill_dir, target_root)[
                        "resolves_in_target_tree"] is not True:
                    f["links_unresolved"].add(link)
            f["unsafe"].update(m.group(0).lower() for m in _UNSAFE_NEW.finditer(line))
        return f

    before, after = facts(original), facts(candidate)
    blocking, notes = [], []
    if after is None:
        return {"verdict": "NOT_PROMOTABLE", "blocking": ["candidate frontmatter unparseable"], "notes": [],
                "checks": {}, "model_calls": 0}
    if before is not None and after["frontmatter"] != before["frontmatter"]:
        blocking.append("frontmatter changed (policy/permission metadata is not adaptable)")
    checks = {
        "host_syntax": {"remaining_placeholders": after["placeholders"], "shell": after["shell"],
                        "claude_vars": sorted(after["claude_vars"])},
        "capability_resolution": {"unresolved_slash_commands": sorted(after["slash_unresolved"]),
                                  "catalog_source": catalog["source"], "expected_key": "/" + qualified.lower()},
        "referenced_resources": {"unresolved": sorted(after["links_unresolved"])},
        "unsupported_dependencies": {"connector_categories": sorted(after["connectors"]),
                                     "tool_lines": after["tool_lines"]},
        "permission_expansion": {"new_sensitive_tokens": sorted(after["unsafe"] - (before["unsafe"] if before else set()))},
    }
    if after["placeholders"] or after["shell"] or after["claude_vars"]:
        blocking.append("unresolved Claude host syntax remains")
    if after["slash_unresolved"]:
        blocking.append("slash command does not resolve in the Hermes catalog: " + ", ".join(sorted(after["slash_unresolved"])))
    if checks["permission_expansion"]["new_sensitive_tokens"]:
        blocking.append("candidate introduces network/tool/credential/shell tokens")
    prior_links = before["links_unresolved"] if before else set()
    prior_conn = before["connectors"] if before else set()
    if after["links_unresolved"] - prior_links:
        blocking.append("candidate introduces unresolved resources")
    elif after["links_unresolved"]:
        notes.append("pre-existing unresolved resources reported, not introduced: " + ", ".join(sorted(after["links_unresolved"])))
    if after["connectors"] - prior_conn or (before and after["tool_lines"] > before["tool_lines"]):
        blocking.append("candidate introduces unsupported dependencies")
    elif after["connectors"]:
        notes.append("pre-existing unsupported connector placeholders remain (SKILLS_ONLY_PARTIAL)")
    return {"verdict": "NOT_PROMOTABLE" if blocking else "PROMOTABLE_TO_REVIEW", "blocking": blocking,
            "notes": notes, "checks": checks, "model_calls": 0,
            "meaning": "PROMOTABLE_TO_REVIEW is not runtime or semantic verification"}


def load_ledger(path: Path | None = None) -> dict:
    path = Path(path) if path is not None else DEFAULT_LEDGER
    if path.is_symlink() or not path.is_file():
        raise PortError("Candidate ledger missing")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != LEDGER_SCHEMA or not isinstance(data.get("rejected"), list):
        raise PortError("Candidate ledger malformed")
    return data


def candidate_gate(root: Path, skill: str, original: bytes, candidate: bytes, *, ledger: dict | None = None) -> dict:
    """Ledger + post-proposal checks; used by uvp_p6_patch.apply_reviewed."""
    ledger = ledger if ledger is not None else load_ledger()
    digest = sha256(candidate)
    catalog = stage_catalog(root)
    # Independent checks always run, so a ledger entry is never the only reason.
    result = check_candidate(original.decode("utf-8"), candidate.decode("utf-8"), skill=skill, catalog=catalog,
                             source_skill_dir=root / "original" / "skills" / skill, source_root=root / "original",
                             target_skill_dir=root / "skills" / skill, target_root=root)
    result["independent_verdict"] = result["verdict"]
    hit = next((r for r in ledger["rejected"] if r.get("candidate_sha256") == digest), None)
    result["ledger_entry"] = hit
    if hit:
        result["verdict"] = "NOT_PROMOTABLE"
        result["blocking"] = ["candidate is recorded as REJECTED in the ledger"] + result["blocking"]
    return result


# --- AI fallback (bounded, approval-gated) --------------------------------

def ai_fallback(ctx, stage: str, skill: str, skill_result: dict, *, approved: bool = False) -> dict:
    """Only for residuals left after deterministic passes. Never applies anything."""
    eligible = [r for r in skill_result.get("residuals", []) if r.get("ai_eligible")]
    if not eligible:
        return {"status": "AI_NOT_NEEDED", "model_calls": 0, "skill": skill}
    if approved is not True:
        return {"status": "HOLD_OPERATOR_APPROVAL_REQUIRED", "model_calls": 0, "skill": skill,
                "residual_count": len(eligible)}
    if {r["kind"] for r in eligible} != {"arguments_placeholder"} or len(eligible) != 1:
        return {"status": "HOLD_NO_BOUNDED_AI_PIPELINE", "model_calls": 0, "skill": skill,
                "residual_kinds": sorted({r["kind"] for r in eligible})}
    if not __package__:
        raise PortError("AI fallback is only available inside the Hermes plugin package")
    from . import uvp_p6_patch
    result = uvp_p6_patch.propose(ctx, stage, skill)
    if result.get("status") == "REVIEW_REQUIRED":
        root, _ = checked_stage(stage)
        before = (root / "skills" / skill / "SKILL.md").read_bytes()
        blob = Path(result["candidate_path"]).read_bytes()
        result["post_proposal_checks"] = candidate_gate(root, skill, before, blob)
    result["applied"] = False
    return result


# --- stage-level run and report -------------------------------------------

def map_stage(stage: str, output: str | None = None, *, registry: dict | None = None,
              identity: dict | None = None, ledger: dict | None = None) -> dict:
    """Map every staged Skill read-only; optionally write candidate files + report to `output`."""
    registry = registry if registry is not None else load_registry()
    identity = identity if identity is not None else default_identity(registry)
    root, porting = checked_stage(stage)
    catalog = stage_catalog(root)
    reviews = {r["skill"]: r for r in porting.get("skill_reviews", [])}
    skills = []
    for skill in catalog["skills"]:
        orig = root / "original" / "skills" / skill / "SKILL.md"
        active = root / "skills" / skill / "SKILL.md"
        if orig.is_symlink() or active.is_symlink() or not orig.is_file() or not active.is_file():
            raise PortError("Unsafe staged Skill path: " + skill)
        ob, ab = orig.read_bytes(), active.read_bytes()
        if sha256(ob) != reviews.get(skill, {}).get("original_sha256"):
            raise PortError("Unverifiable original Skill: " + skill)
        res = map_skill_text(ab.decode("utf-8"), skill=skill, catalog=catalog, registry=registry, identity=identity,
                             source_skill_dir=orig.parent, source_root=root / "original",
                             target_skill_dir=active.parent, target_root=root)
        mapped = res.pop("mapped_text").encode("utf-8")
        res.update({
            "source_path": "original/skills/%s/SKILL.md" % skill,
            "active_path": "skills/%s/SKILL.md" % skill,
            "original_sha256": sha256(ob), "active_sha256": sha256(ab),
            "active_equals_original": ab == ob, "mapped_sha256": sha256(mapped),
            "verification": _axes_for(res),
        })
        skills.append((res, mapped))
    candidates = []
    cand_dir = root / "P6_REVIEW_CANDIDATES"
    if cand_dir.is_dir() and not cand_dir.is_symlink():
        led = ledger if ledger is not None else load_ledger()
        for meta_file in sorted(cand_dir.glob("*.json")):
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            skill = meta.get("skill")
            md = cand_dir / (str(skill) + ".md")
            if skill not in catalog["skills"] or md.is_symlink() or not md.is_file():
                continue
            blob = md.read_bytes()
            gate = candidate_gate(root, skill, (root / "skills" / skill / "SKILL.md").read_bytes(), blob, ledger=led)
            gate.update({"skill": skill, "candidate_sha256": sha256(blob),
                         "recorded_candidate_sha256": meta.get("candidate_sha256"), "preserved_unmodified": True})
            candidates.append(gate)
    per = [s for s, _ in skills]
    report = {
        "schema": REPORT_SCHEMA, "engine_version": ENGINE_VERSION,
        "registry": {"version": registry["registry_version"], "sha256": registry["sha256"],
                     "target_probe_sha256": registry["probe_sha256"]},
        "identity": identity, "stage_path": str(root),
        "stage_source_fingerprint_sha256": porting.get("source_fingerprint_sha256"),
        "declared_source_commit_unverified": porting.get("declared_source_commit_unverified"),
        "catalog": catalog,
        "rules_applied": sorted({(m["rule_id"], m["rule_version"]) for s in per for m in s["matches"]
                                 if m["outcome"] in {"APPLIED", "IDENTITY", "ALREADY_MAPPED"}}),
        "counts": {
            "skills": len(per),
            "direct_exact_regions": sum(1 for s in per for m in s["matches"] if m["kind"] == "direct"),
            "composed_mappings_applied": sum(1 for s in per for m in s["matches"]
                                             if m["kind"] == "composition" and m["outcome"] == "APPLIED"),
            "composed_already_mapped": sum(1 for s in per for m in s["matches"]
                                           if m["kind"] == "composition" and m["outcome"] == "ALREADY_MAPPED"),
            "provisional_verifications": sum(len(s["provisional"]) for s in per),
            "unresolved_residuals": sum(len(s["residuals"]) for s in per),
            "ai_eligible_residuals": sum(1 for s in per for r in s["residuals"] if r["ai_eligible"]),
            "unsupported_items": sum(len(s["unsupported"]) for s in per),
            "files_changed": sum(1 for s in per if s["changed"]),
            "holds": sum(1 for s in per if s["status"] == "HOLD"),
        },
        "model_calls": 0,
        "unsupported_capabilities": {
            "connectors": sorted(porting.get("unported_connector_names", [])),
            "components": porting.get("unsupported_source_components", []),
            "classification": porting.get("status"),
        },
        "skills": per,
        "existing_review_candidates": candidates,
        "writes_inside_stage": False,
        "installation_performed": False, "execution_performed": False,
        "limitations": [
            "Runtime compatibility is NOT verified: no Hermes session loaded these Skills.",
            "Semantic equivalence is NOT established for any rule; R-D001 guarantees identical input text only.",
            "Target identity is the probed Hermes source checkout; the installed Hermes binary was not compared.",
            "Catalog resolution is static (generated __init__.py), not the live Hermes catalog.",
            "Mapped files are review candidates outside the stage; nothing was applied to the stage.",
        ],
    }
    if output:
        out = Path(output).expanduser().resolve()
        if out.exists():
            raise PortError("Output directory already exists; refusing to overwrite")
        if out == root or out.is_relative_to(root) or root.is_relative_to(out):
            raise PortError("Output may not overlap the stage")
        out.mkdir(parents=True)
        for res, mapped in skills:
            if res["changed"]:
                p = out / "skills" / res["skill"] / "SKILL.md"
                p.parent.mkdir(parents=True)
                with p.open("xb") as f:
                    f.write(mapped)
        with (out / "COMPAT_REPORT.json").open("xb") as f:
            f.write(_canon(report))
        with (out / "COMPAT_REPORT.md").open("xb") as f:
            f.write(render_markdown(report).encode("utf-8"))
    return report


def render_markdown(report: dict) -> str:
    c = report["counts"]
    out = ["# P6 compatibility mapping report", "",
           "Engine `%s`, registry `%s` (sha256 `%s`)." % (report["engine_version"], report["registry"]["version"],
                                                          report["registry"]["sha256"]),
           "Source semantics `%s`; target `%s`." % (report["identity"]["source"], report["identity"]["target"]),
           "Stage fingerprint `%s`; declared upstream commit `%s` (declared, not independently linked)." % (
               report["stage_source_fingerprint_sha256"], report["declared_source_commit_unverified"]),
           "", "**Model calls: %d.** Writes inside the stage: %s. Installation: %s." % (
               report["model_calls"], report["writes_inside_stage"], report["installation_performed"]), "",
           "| Count | Value |", "|---|---|"]
    out += ["| %s | %s |" % (k, v) for k, v in sorted(c.items())]
    out += ["", "Rules applied: " + ", ".join("%s v%d" % r for r in report["rules_applied"]), "",
            "## Per Skill", "",
            "| Skill | Original SHA-256 | Status | Changed | Structural | Runtime | Semantic | Residuals |",
            "|---|---|---|---|---|---|---|---|"]
    for s in report["skills"]:
        v = s["verification"]
        structural = v["structural"] + (" (" + ", ".join(v["structural_gaps"]) + ")" if v["structural_gaps"] else "")
        out.append("| %s | `%s` | %s | %s | %s | %s | %s | %d |" % (
            s["skill"], s["original_sha256"][:16] + "...", s["status"], s["changed"], structural,
            v["runtime"].split(" ")[0], v["semantic"], len(s["residuals"])))
    out += ["", "## Exact deltas", ""]
    for s in report["skills"]:
        for d in s["deltas"]:
            out += ["- `%s` line %d via %s v%d" % (s["active_path"], d["line"], d["rule_id"], d["rule_version"]),
                    "  - old: `%s`" % d["old"], "  - new: `%s`" % d["new"]]
        if s["changed"]:
            out.append("  - sha256 %s -> %s" % (s["active_sha256"], s["mapped_sha256"]))
    out += ["", "## Unresolved residuals", ""]
    for s in report["skills"]:
        for r in s["residuals"]:
            out.append("- %s line %d `%s`: %s (attempted: %s; AI eligible: %s)" % (
                s["skill"], r["span"]["start_line"], r["kind"], r["reason"],
                ", ".join(r["attempted_rule_ids"]) or "none", r["ai_eligible"]))
    out += ["", "## Unsupported", "",
            "Classification: **%s**. Connectors not ported: %s." % (
                report["unsupported_capabilities"]["classification"],
                ", ".join(report["unsupported_capabilities"]["connectors"]) or "none"), ""]
    for s in report["skills"]:
        cats = sorted({u["category"] for u in s["unsupported"] if u["kind"] == "connector_placeholder"})
        keys = sorted({u["key"] for u in s["unsupported"] if "key" in u})
        if cats or keys:
            out.append("- %s: connector placeholders [%s]; frontmatter not preserved [%s]" % (
                s["skill"], ", ".join(cats), ", ".join(keys)))
    out += ["", "## Existing review candidates (preserved, not modified)", ""]
    for cnd in report["existing_review_candidates"]:
        out.append("- %s `%s`: **%s**. %s" % (cnd["skill"], cnd["candidate_sha256"], cnd["verdict"],
                                               "; ".join(cnd["blocking"])))
    out += ["", "## Limitations", ""] + ["- " + x for x in report["limitations"]]
    out.append("")
    return "\n".join(out)
