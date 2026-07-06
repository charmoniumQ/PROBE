#!/bin/bash
set -e

echo "=== Downloading data (tiny) ==="
python /scripts/10-download.py \
    --train-split 'train[:0.1%]' \
    --val-split 'validation[:0.1%]' \
    2>/dev/null

echo "=== Tokenizing (tiny) ==="
python /scripts/20-tokenizer.py 2>/dev/null

echo "=== Creating batches (tiny) ==="
python /scripts/25-batch.py \
    --max-tokens 32 \
    --buffer-size 500 \
    --batch-size 4 \
    2>/dev/null

echo "=== Training (tiny) ==="
python /scripts/50-train.py \
    --num-layers 1 \
    --d-model 64 \
    --dff 128 \
    --num-heads 2 \
    --epochs 1 \
    --warmup-steps 100 \
    2>/dev/null

echo "=== Inference (tiny) ==="
python /scripts/60-inference.py --max-tokens 32 2>/dev/null \
    | grep -E 'Input:|Prediction:|Ground truth'

echo "=== Done (tiny) ==="
