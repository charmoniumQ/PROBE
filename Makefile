all:
		mkdir -p experiments

	# Process 14194128: bash -c cat flake.nix > test0; head test0 >tmp ; wc -l <tmp
		mkdir -p process_14194128
	# Run command for process 14194128
		(bash -c cat flake.nix > test0; head test0 >tmp ; wc -l <tmp) > process_14194128/output.log 2>&1
	# Process 14194128: cat flake.nix
		mkdir -p process_14194128
	# Copy input files for process 14194128
		cp flake.nix_v0 process_14194128/
	# Run command for process 14194128
		(cd process_14194128 && cat flake.nix)
	# Process 14194128: head test0
		mkdir -p process_14194128
	# Copy input files for process 14194128
		cp test0_v0 process_14194128/
	# Run command for process 14194128
		(cd process_14194128 && head test0)
	# Process 14194128: wc -l
		mkdir -p process_14194128
	# Copy input files for process 14194128
		cp tmp_v0 process_14194128/
	# Run command for process 14194128
		(wc -l) > process_14194128/output.log 2>&1