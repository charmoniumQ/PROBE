#!/bin/bash
# This bash script generates an example dataflow graph with multiple processes and files

# Input and output files
INPUT_FILE="input.txt"
TEMP_FILE1="temp1.txt"
TEMP_FILE2="temp2.txt"
OUTPUT_FILE="output.txt"

#Create input file if not already provided
if [ ! -f "$INPUT_FILE" ]; then
    echo "Creating input file: $INPUT_FILE"
    cat <<EOL > "$INPUT_FILE"
hello world
this is a test
bash scripting is powerful
EOL
fi

#Reader process - Reads and writes to TEMP_FILE1
echo "Running Reader process..."
cat "$INPUT_FILE" > "$TEMP_FILE1"
if [ $? -ne 0 ]; then
    echo "Error: Reader process failed."
    exit 1
fi

#  process converts to uppercase and writes to TEMP_FILE2
echo "Running Transformer process..."
awk '{ print toupper($0) }' "$TEMP_FILE1" > "$TEMP_FILE2"
if [ $? -ne 0 ]; then
    echo "Error: Transformer process failed."
    exit 1
fi

# Process writes final output to OUTPUT_FILE
echo "Running Writer process..."
cat "$TEMP_FILE2" > "$OUTPUT_FILE"
if [ $? -ne 0 ]; then
    echo "Error: Writer process failed."
    exit 1
fi

echo "Pipeline complete. Output written to $OUTPUT_FILE"
echo "Contents of $OUTPUT_FILE:"
cat "$OUTPUT_FILE"