#!/usr/bin/env bash
# install.sh — clone ds000114 v1.0.2 + fetch a single subject's T1w
#
# Storage cost: ~30 MB (just sub-01 T1w + dataset metadata)
# Time cost:    ~1 minute on a reasonable connection
#
# Usage:  bash install.sh [DATA_DIR]
#         (default DATA_DIR: ~/data/ds000114)

set -euo pipefail

DATA_DIR="${1:-${HOME}/data/ds000114}"
DATASET_URL="///openneuro/ds000114"
SUBJECT="sub-01"
SESSION="ses-test"

step() { echo; echo "━━━ $1 ━━━"; }
ok()   { echo "  ✓ $1"; }
fail() { echo "✗ $1" >&2; exit 1; }

step "STEP 0 — check dependencies"
command -v datalad >/dev/null 2>&1 || fail "datalad not installed. Run: pip install datalad"
ok "datalad: $(datalad --version | head -1)"

step "STEP 1 — clone ds000114 superdataset"
mkdir -p "$(dirname "$DATA_DIR")"
if [ -d "$DATA_DIR/.datalad" ]; then
  ok "$DATA_DIR already exists; skipping clone"
else
  datalad install -s "$DATASET_URL" "$DATA_DIR" \
    || fail "datalad install failed. Check network + the dataset URL."
  ok "cloned to $DATA_DIR"
fi

step "STEP 2 — fetch $SUBJECT $SESSION T1w content"
cd "$DATA_DIR"
T1W_PATH="${SUBJECT}/${SESSION}/anat/${SUBJECT}_${SESSION}_T1w.nii.gz"
if [ ! -f "$T1W_PATH" ] || [ ! -s "$T1W_PATH" ]; then
  datalad get "$T1W_PATH" || fail "datalad get failed for $T1W_PATH"
  ok "fetched $T1W_PATH"
else
  ok "$T1W_PATH already present"
fi

step "STEP 3 — record DataLad coordinates for the Glimmer graph"
COMMIT_SHA=$(git rev-parse HEAD)
ANNEX_KEY=$(git annex lookupkey "$T1W_PATH" 2>/dev/null || echo "unknown")
echo "  superdataset:           $DATASET_URL"
echo "  local path:             $DATA_DIR"
echo "  commit SHA:             $COMMIT_SHA"
echo "  T1w relative path:      $T1W_PATH"
echo "  T1w git-annex key:      $ANNEX_KEY"

# Persist for downstream scripts
cat > "$DATA_DIR/.glimmer-coordinates.json" <<EOF
{
  "datalad-superdataset": "$DATASET_URL",
  "local-path": "$DATA_DIR",
  "datalad-commit-sha": "$COMMIT_SHA",
  "t1w-relative-path": "$T1W_PATH",
  "t1w-annex-key": "$ANNEX_KEY",
  "subject": "$SUBJECT",
  "session": "$SESSION"
}
EOF
ok "wrote $DATA_DIR/.glimmer-coordinates.json"

step "STEP 4 — DONE"
echo
echo "Next: run the Nipype workflow"
echo "    python workflow.py"
echo
