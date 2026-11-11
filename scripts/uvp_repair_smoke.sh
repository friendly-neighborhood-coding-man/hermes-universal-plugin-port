#!/usr/bin/env bash
# End-to-end smoke of the released workflow on a DISPOSABLE Hermes home (TEST DRIVER approvals; no model calls):
#   official Hermes importer -> uvp_repair.py doctor -> plan -> candidate -> apply -> verify -> rollback -> verify
# usage: scripts/uvp_repair_smoke.sh HOME(.uvp-disposable, bootstrapped) OFFICIAL_IMPORTER_DIR ANTHROPIC_CLONE(@e605d8dd) NEW_WORK_DIR
set -eu
H="$1"; OFF="$2"; ANT="$3"; W="$4"
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
w() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
[ -f "$H/.uvp-disposable" ] || { echo "home is not marked .uvp-disposable"; exit 2; }
mkdir -p "$W/source/.claude/skills"
cp -r "$ANT/product-management/skills/synthesize-research" "$W/source/.claude/skills/"
printf '# Project guidance\n\nCite interview IDs for every finding.\n' > "$W/source/.claude/CLAUDE.md"
D=$(python -c "import sys;sys.path.insert(0,'.');from scripts.p615_preview_official_import import package_digest;print(package_digest(__import__('pathlib').Path(sys.argv[1])))" "$(w "$OFF")")
# Resolve the Hermes runtime BEFORE the preflight: running Hermes writes into the home.
RT=$(python -c "import sys;sys.path.insert(0,'.');import uvp_repair as U;s,p=U.hermes_runtime(__import__('pathlib').Path(sys.argv[1]));print(s+'|'+p)" "$(w "$H")")
HSRC="${RT%%|*}"; HPY="${RT##*|}"
echo "== 1. official import: preview receipt"
python scripts/p615_preview_official_import.py --official-package "$(w "$OFF")" --package-sha256 "$D" --agent claude-code \
  --source "$(w "$W/source/.claude")" --target "$(w "$H")" --memory-limit 2200 --output "$(w "$W/import-preflight.json")" --i-confirm-disposable-home > "$W/import-preflight.out"
RH=$(python -c "import json,sys;print(json.load(open(sys.argv[1]))['receipt_sha256'])" "$W/import-preflight.json")
echo "== 1b. official import: execute (official AgentImporter) + postflight"
python scripts/p615_apply_official_import.py --official-package "$(w "$OFF")" --package-sha256 "$D" --agent claude-code \
  --source "$(w "$W/source/.claude")" --target "$(w "$H")" --receipt "$(w "$W/import-preflight.json")" --approve-receipt-sha256 "$RH" \
  --backup-dir "$(w "$W/import-backup")" --output "$(w "$W/import-postflight.json")" --i-approve-test-apply --hermes-python "$HPY" --hermes-src "$HSRC" > "$W/import-apply.out" || true
python -c "import json,sys;d=json.load(open(sys.argv[1]));print('import final gate:',d['final_gate'],d['postflight']['gates'])" "$W/import-postflight.json"
R="$W/repair"
echo "== 2. doctor";    python uvp_repair.py doctor --home "$(w "$H")" --work "$(w "$R")" --origin "synthesize-research=$(w "$ANT")::product-management/skills/synthesize-research" | tee "$W/2-doctor.json"
echo "== 3. plan";      python uvp_repair.py plan --work "$(w "$R")" | tee "$W/3-plan.json"
F=$(python -c "import json,sys;print(next(p['finding_id'] for p in json.load(open(sys.argv[1]))['proposals'] if p['classification']=='DETERMINISTIC_REPAIR_AVAILABLE'))" "$W/3-plan.json")
echo "== 4. candidate $F"; python uvp_repair.py candidate --work "$(w "$R")" --finding "$F" | tee "$W/4-candidate.json"
CD=$(python -c "import json,sys;print(json.load(open(sys.argv[1]))['candidate_digest'])" "$W/4-candidate.json")
echo "== 4b. wrong digest must HOLD"; ! python uvp_repair.py apply --work "$(w "$R")" --finding "$F" --approve-digest "$(printf '0%.0s' {1..64})" --test-driver
echo "== 4c. non-TTY operator apply must HOLD"; ! python uvp_repair.py apply --work "$(w "$R")" --finding "$F" --approve-digest "$CD" < /dev/null
echo "== 5. apply (TEST DRIVER)"; python uvp_repair.py apply --work "$(w "$R")" --finding "$F" --approve-digest "$CD" --test-driver | tee "$W/5-apply.json"
echo "== 5b. replay must HOLD"; ! python uvp_repair.py apply --work "$(w "$R")" --finding "$F" --approve-digest "$CD" --test-driver
echo "== 6. verify";    python uvp_repair.py verify --work "$(w "$R")" | tee "$W/6-verify.json"
echo "== 7. rollback";  python uvp_repair.py rollback --work "$(w "$R")" --finding "$F" | tee "$W/7-rollback.json"
echo "== 8. official import rollback"; python scripts/p615_apply_official_import.py --rollback "$(w "$W/import-backup")" --target "$(w "$H")" > "$W/8-import-rollback.json" || true
echo SMOKE_DONE
