#!/bin/bash
set -e

echo "=== Downloading data (small) ==="
python /scripts/10-download.py \
    --train-split 'train[:0.5%]' \
    --val-split 'validation[:0.5%]' \
    2>/dev/null

echo "=== Tokenizing (small) ==="
python /scripts/20-tokenizer.py 2>/dev/null

echo "=== Creating batches (small) ==="
python /scripts/25-batch.py \
    --max-tokens 64 \
    --buffer-size 2000 \
    --batch-size 8 \
    2>/dev/null

echo "=== Training (small) ==="
python /scripts/50-train.py \
    --num-layers 2 \
    --d-model 96 \
    --dff 256 \
    --num-heads 4 \
    --epochs 1 \
    --warmup-steps 500 \
    2>/dev/null

echo "=== Inference (small) ==="
python /scripts/60-inference.py --max-tokens 64 2>/dev/null \
    | grep -E 'Input:|Prediction:|Ground truth'

echo "=== Done (small) ==="
