set -ex

# python=".venv/bin/python"
# scratch=./data2
python="python"
scratch=/scratch

# mkdir --parents $scratch

"$python" download_data.py --data-dir "$scratch/data"
data1="$scratch/data/eng-fra1.txt"
shuf -n 1000 "$scratch/data/eng-fra.txt" -o "$data1"

data2="$scratch/data/eng-fra2.txt"
shuf -n 1000 "$scratch/data/eng-fra.txt" -o "$data2"

"$python" download_data.py --data-dir "$scratch/data" --anki fra
data3="$scratch/data/eng-fra3.txt"
shuf -n 100 "$scratch/data/eng-fra.txt" -o "$data3"

data4="$scratch/data/eng-fra4.txt"
shuf -n 100 "$scratch/data/eng-fra.txt" -o "$data4"

data1_clean="$scratch/data/data1_clean.txt"
"$python" clean_data.py --input $data1 --output $data1_clean --max-length 5 --report-dir "$scratch/clean-data" --lang1 eng --lang2 fra

data2_clean="$scratch/data/data2_clean.txt"
"$python" clean_data.py --input $data2 --output $data2_clean --max-length 4 --report-dir "$scratch/clean-data" --lang1 eng --lang2 fra

data3_clean="$scratch/data/data3_clean.txt"
"$python" clean_data.py --input $data3 --output $data3_clean --normalize --max-length 6 --report-dir "$scratch/clean-data_final" --lang1 eng --lang2 fra

data4_clean="$scratch/data/data4_clean.txt"
"$python" clean_data.py --input $data2 --output $data4_clean --normalize --report-dir "$scratch/clean-data_november" --lang1 eng --lang2 fra

"$python" verify_datasets.py $data2_clean $data3_clean --max-length 10 --seed 1 --report-dir $scratch/verify1

"$python" verify_datasets.py $data2_clean $data3_clean --max-length 1 --seed 10 --report-dir $scratch/verify2

"$python" verify_datasets.py $data2_clean $data4_clean --max-length 1 --seed 10 --report-dir $scratch/verify3

epochs=2
batch_size=32
lr=0.001

mv $data1_clean $scratch/data/eng-fra.txt
"$python" train.py --arch "rnn" --size "tiny" --epochs "$epochs" --batch-size "$batch_size" --lr "$lr" --output-dir "$scratch/train" --lang1 eng --lang2 fra --data-dir "$scratch/data" --run-name v1

mv $data2_clean $scratch/data/eng-fra.txt
"$python" train.py --arch "rnn" --size "tiny" --epochs "$epochs" --batch-size "$batch_size" --lr "$lr" --output-dir "$scratch/train" --lang1 eng --lang2 fra --data-dir "$scratch/data" --run-name v2

mv $data2_clean $scratch/data/eng-fra.txt
"$python" train.py --arch "bahdanau" --size "tiny" --epochs "$epochs" --batch-size "$batch_size" --lr "$lr" --output-dir "$scratch/train" --lang1 eng --lang2 fra --data-dir "$scratch/data" --run-name v3

lr=0.01
mv $data1_clean $scratch/data/eng-fra.txt
"$python" train.py --arch "bahdanau" --size "tiny" --epochs "$epochs" --batch-size "$batch_size" --lr "$lr" --output-dir "$scratch/train" --lang1 eng --lang2 fra --data-dir "$scratch/data" --run-name v4

"$python" compare.py "$scratch/train/run_v1" "$scratch/train/run_v2" --output-dir "$scratch/comparison"
"$python" compare.py "$scratch/train/run_v1" "$scratch/train/run_v3" --output-dir "$scratch/comparison"

run_dir="$scratch/train/run_v1"
count=10
mkdir "$scratch/inferrence"
grep '^> ' "$run_dir/samples.txt" | sed 's/^> //' | shuf -n "$count" | "$python" evaluate.py --run-dir "$run_dir" --interactive > "$scratch/inferrence/p1"

run_dir="$scratch/train/run_v1"
count=100
grep '^> ' "$run_dir/samples.txt" | sed 's/^> //' | shuf -n "$count" | "$python" evaluate.py --run-dir "$run_dir" --interactive > "$scratch/inferrence/p2"

run_dir="$scratch/train/run_v3"
count=10
grep '^> ' "$run_dir/samples.txt" | sed 's/^> //' | shuf -n "$count" | "$python" evaluate.py --run-dir "$run_dir" --interactive > "$scratch/inferrence/p3"
