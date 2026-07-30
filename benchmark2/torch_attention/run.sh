#!/usr/bin/env bash
#
# End-to-end driver (shell port of the former run.py).
#
# Steps:
#   0. Data prep: download (if missing), clean, and verify datasets.
#   1. Train the architecture x size grid (train.py) into a runs directory.
#   2. Compare the trained run directories with compare.py (dir name = model).
#   3. Demo translation through evaluate.py's interactive (stdin) mode.
#
# Pipe / stdin-stdout redirection patterns used:
#   (1) tee          - every python step is tee'd to a per-step log while
#                      still streaming to the console.
#   (2) grep|sed|sort- the per-run "--- <name>: ..." summaries are ranked by
#                      val_loss into a leaderboard (hoist key, sort, drop key).
#   (3) grep|tee     - the markdown comparison table is sliced straight out of
#                      compare.py's stdout into the comparison dir.
#   (4) stdin pipe   - sampled source sentences are piped
#                      (grep|sed|shuf) into evaluate.py --interactive.
#
set -euo pipefail -x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ------------------------------- defaults --------------------------------
ARCHS_STR="rnn bahdanau luong"
COMPARE_SIZES_STR="tiny small"
LANG1="eng"
LANG2="fra"
REVERSE=1
DATA_DIR="data"
EPOCHS=20
BATCH_SIZE=32
LR=0.001
MAX_PAIRS=""
DEVICE=""
OUTPUT_DIR="artifacts"
SECONDARY=""          # e.g. "spa" -> data/eng-spa.txt, used for verify
DOWNLOAD=0            # allow network downloads for missing data
SKIP_PREFLIGHT=0
SKIP_TRAIN=0          # skip grid training; let compare.py train instead
DEMO=1
DEMO_COUNT=5

usage() {
  cat <<'EOF'
Usage: run.sh [options]

  --archs "A B C"          Architectures                 (default: "rnn bahdanau luong")
  --compare-sizes "S1 S2"  Sizes for the grid/comparison (default: "tiny small")
  --lang1 CODE             First language code           (default: eng)
  --lang2 CODE             Second language code          (default: fra)
  --reverse | --no-reverse Translate lang2->lang1        (default: --reverse)
  --data-dir DIR           Data directory                (default: data)
  --epochs N               Epochs                        (default: 20)
  --batch-size N           Batch size                    (default: 32)
  --lr F                   Learning rate                 (default: 0.001)
  --max-pairs N            Cap on #pairs                 (default: unset)
  --device DEV             cpu / cuda / auto             (default: auto)
  --output-dir DIR         Artifact root                 (default: artifacts)
  --secondary LANG         Secondary eng-<LANG> set for the verify step (e.g. spa)
  --download               Allow downloading missing datasets
  --skip-preflight         Skip download/clean/verify
  --skip-train             Skip grid training; compare whatever runs already exist
  --demo | --no-demo       Run the stdin translation demo (default: --demo)
  --demo-count N           #sentences to translate       (default: 5)
  -h, --help               Show this help

Set the PYTHON env var to choose the interpreter (defaults to ./.venv/bin/python).
EOF
}

# ------------------------------ arg parsing ------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --archs)          ARCHS_STR="$2"; shift 2;;
    --compare-sizes)  COMPARE_SIZES_STR="$2"; shift 2;;
    --lang1)          LANG1="$2"; shift 2;;
    --lang2)          LANG2="$2"; shift 2;;
    --reverse)        REVERSE=1; shift;;
    --no-reverse)     REVERSE=0; shift;;
    --data-dir)       DATA_DIR="$2"; shift 2;;
    --epochs)         EPOCHS="$2"; shift 2;;
    --batch-size)     BATCH_SIZE="$2"; shift 2;;
    --lr)             LR="$2"; shift 2;;
    --max-pairs)      MAX_PAIRS="$2"; shift 2;;
    --device)         DEVICE="$2"; shift 2;;
    --output-dir)     OUTPUT_DIR="$2"; shift 2;;
    --secondary)      SECONDARY="$2"; shift 2;;
    --download)       DOWNLOAD=1; shift;;
    --skip-preflight) SKIP_PREFLIGHT=1; shift;;
    --skip-train)     SKIP_TRAIN=1; shift;;
    --demo)           DEMO=1; shift;;
    --no-demo)        DEMO=0; shift;;
    --demo-count)     DEMO_COUNT="$2"; shift 2;;
    -h|--help)        usage; exit 0;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2;;
  esac
done

read -ra ARCHS <<< "$ARCHS_STR"
read -ra COMPARE_SIZES <<< "$COMPARE_SIZES_STR"

# ------------------------------ interpreter ------------------------------
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x ".venv/bin/python" ]; then PYTHON=".venv/bin/python"; else PYTHON="python3"; fi
fi

LOG_DIR="$OUTPUT_DIR/logs"
GRID_DIR="$OUTPUT_DIR/runs"          # per-cell training runs
CMP_DIR="$OUTPUT_DIR/comparison"     # aggregated comparison artifacts
mkdir -p "$LOG_DIR" "$GRID_DIR" "$CMP_DIR"

PRIMARY_FILE="$DATA_DIR/${LANG1}-${LANG2}.txt"
SECONDARY_FILE=""
[ -n "$SECONDARY" ] && SECONDARY_FILE="$DATA_DIR/eng-${SECONDARY}.txt"

# Shared data/task arguments forwarded to the Python entry points.
DATA_ARGS=(--lang1 "$LANG1" --lang2 "$LANG2" --data-dir "$DATA_DIR")
if [ "$REVERSE" -eq 1 ]; then DATA_ARGS+=(--reverse); else DATA_ARGS+=(--no-reverse); fi
[ -n "$MAX_PAIRS" ] && DATA_ARGS+=(--max-pairs "$MAX_PAIRS")
[ -n "$DEVICE" ] && DATA_ARGS+=(--device "$DEVICE")

# Rank per-run summaries ("--- <name>: ...") by val_loss: strip the prefix,
# hoist val_loss as a sort key, sort numerically, drop the key, tee to file.
build_leaderboard() {
  grep -h '^--- ' "$LOG_DIR"/train_*.log 2>/dev/null \
    | sed -E 's/^--- //' \
    | sed -E 's/.*val_loss=([0-9.]+).*/\1\t&/' \
    | sort -n \
    | cut -f2- \
    | tee "$OUTPUT_DIR/leaderboard.txt"
}

# ----------------------- Step 0: data preflight --------------------------
if [ "$SKIP_PREFLIGHT" -eq 0 ]; then
  echo
  echo "########## Step 0: data preflight (download / clean / verify) ##########"

  # -- download (only if missing) --
  if [ ! -f "$PRIMARY_FILE" ]; then
    if [ "$DOWNLOAD" -eq 1 ]; then
      echo "\$ $PYTHON download_data.py --output $PRIMARY_FILE"
      "$PYTHON" download_data.py --output "$PRIMARY_FILE" 2>&1 | tee "$LOG_DIR/download_primary.log"
    else
      echo "ERROR: $PRIMARY_FILE missing. Re-run with --download." >&2
      exit 1
    fi
  fi
  if [ -n "$SECONDARY_FILE" ] && [ ! -f "$SECONDARY_FILE" ]; then
    if [ "$DOWNLOAD" -eq 1 ]; then
      echo "\$ $PYTHON download_data.py --anki $SECONDARY --output $SECONDARY_FILE"
      "$PYTHON" download_data.py --anki "$SECONDARY" --output "$SECONDARY_FILE" 2>&1 \
        | tee "$LOG_DIR/download_secondary.log"
    else
      echo "(secondary $SECONDARY_FILE missing; pass --download to fetch it)"
    fi
  fi

  # -- clean (torch-free) --
  echo "\$ $PYTHON clean_data.py --input $PRIMARY_FILE ... | tee $LOG_DIR/clean_primary.log"
  "$PYTHON" clean_data.py --input "$PRIMARY_FILE" \
    --output "$OUTPUT_DIR/clean/$(basename "${PRIMARY_FILE%.txt}").clean.txt" \
    --normalize --report-dir "$OUTPUT_DIR/clean/primary" 2>&1 \
    | tee "$LOG_DIR/clean_primary.log"
  if [ -n "$SECONDARY_FILE" ] && [ -f "$SECONDARY_FILE" ]; then
    "$PYTHON" clean_data.py --input "$SECONDARY_FILE" \
      --output "$OUTPUT_DIR/clean/$(basename "${SECONDARY_FILE%.txt}").clean.txt" \
      --normalize --report-dir "$OUTPUT_DIR/clean/secondary" 2>&1 \
      | tee "$LOG_DIR/clean_secondary.log"
  fi

  # -- verify (torch-free) -- needs two datasets --
  if [ -n "$SECONDARY_FILE" ] && [ -f "$SECONDARY_FILE" ]; then
    echo "\$ $PYTHON verify_datasets.py $PRIMARY_FILE $SECONDARY_FILE | tee $LOG_DIR/verify.log"
    "$PYTHON" verify_datasets.py "$PRIMARY_FILE" "$SECONDARY_FILE" \
      --report-dir "$OUTPUT_DIR/verify" 2>&1 | tee "$LOG_DIR/verify.log"
  else
    echo "(skipping verify: need a --secondary dataset to compare against)"
  fi
fi

# --------------------- Step 1: train the arch x size grid ----------------
if [ "$SKIP_TRAIN" -eq 0 ]; then
  echo
  echo "########## Step 1: train grid (archs x sizes) ##########"
  for arch in "${ARCHS[@]}"; do
    for size in "${COMPARE_SIZES[@]}"; do
      log="$LOG_DIR/train_${arch}_${size}.log"
      echo
      echo "\$ $PYTHON train.py --arch $arch --size $size ... | tee $log"
      echo "--------------------------------------------------------------------------------"
      "$PYTHON" train.py \
        --arch "$arch" --size "$size" \
        --epochs "$EPOCHS" --batch-size "$BATCH_SIZE" --lr "$LR" \
        --output-dir "$GRID_DIR" \
        "${DATA_ARGS[@]}" 2>&1 | tee "$log"
    done
  done

  echo
  echo "---- leaderboard by val_loss (best first) ----"
  build_leaderboard || true
fi

# ------------- Step 2: compare the trained run directories ---------------
# compare.py takes a list of run dirs; each dir's basename is the model name.
echo
echo "########## Step 2: architecture comparison ##########"
compare_log="$LOG_DIR/compare.log"
DEMO_BASE="$GRID_DIR"
shopt -s nullglob
run_dirs=("$GRID_DIR"/*/)
shopt -u nullglob
if [ "${#run_dirs[@]}" -eq 0 ]; then
  echo "No run directories under $GRID_DIR to compare (did training run?)." >&2
else
  echo "\$ $PYTHON compare.py ${run_dirs[*]} --output-dir $CMP_DIR | tee $compare_log"
  echo "--------------------------------------------------------------------------------"
  "$PYTHON" compare.py "${run_dirs[@]}" --output-dir "$CMP_DIR" 2>&1 | tee "$compare_log"

  # Pull just the markdown comparison table out of compare.py's stdout.
  echo
  echo "---- comparison table (extracted from stdout) ----"
  grep -E '^\|' "$compare_log" | tee "$CMP_DIR/table.md" || true
fi

# ------------------- Step 3: stdin -> stdout translation demo -------------
# Sample in-vocabulary source sentences from the first grid cell's samples.txt
# ("> <source>" lines) and pipe them into evaluate.py's interactive mode.
if [ "$DEMO" -eq 1 ]; then
  demo_arch="${ARCHS[0]}"
  demo_size="${COMPARE_SIZES[0]}"
  run_name="${LANG1}-${LANG2}"
  [ "$REVERSE" -eq 1 ] && run_name="${run_name}-rev"
  run_name="${run_name}_${demo_arch}_${demo_size}"
  run_dir="$DEMO_BASE/$run_name"
  samples_file="$run_dir/samples.txt"

  if [ -f "$run_dir/model.pt" ] && [ -f "$samples_file" ]; then
    echo
    echo "########## Step 3: translate $DEMO_COUNT sampled sentences (stdin -> evaluate.py) ##########"
    echo "\$ grep '^> ' $samples_file | sed 's/^> //' | shuf -n $DEMO_COUNT | $PYTHON evaluate.py --run-dir $run_dir --interactive"
    echo "--------------------------------------------------------------------------------"
    grep '^> ' "$samples_file" \
      | sed 's/^> //' \
      | shuf -n "$DEMO_COUNT" \
      | "$PYTHON" evaluate.py --run-dir "$run_dir" --interactive \
      || true
  fi
fi

echo
echo "All done. See '$OUTPUT_DIR/' for outputs (logs in '$LOG_DIR/')."
