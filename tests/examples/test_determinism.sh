set -e -x

function test() {
    id=$1
    shift
    cmd=$@

    echo -n "${id}" > test_files/contents
    rm -f test_files/inode
    echo "hi" > test_files/inode

    umask "00${id}"

    if [ -d test_files/disorderfs ]; then
        umount test_files/disorderfs
        rmdir test_files/disorderfs
    fi
    mkdir test_files/disorderfs
    ../result/bin/disorderfs --shuffle-dirents=yes test_files/disorderfs_source test_files/disorderfs

    env test_env_var="${id}" ${cmd}
}

if [ ! -d test_files ]; then
    mkdir -p test_files
fi

if [ ! -d test_files/disorderfs_source ]; then
    mkdir -p test_files/disorderfs_source
    for i in $(seq 20); do
        touch test_files/disorderfs_source/$i
    done
fi

../result/bin/g++ -mrdrnd -Wall -Wextra test_determinism.cxx -o test_files/test_determinism

test 0 ./test_files/test_determinism > test_files/out.native.0
test 2 ./test_files/test_determinism > test_files/out.native.1
echo "====== Native ======"
../result/bin/icdiff --whole-file test_files/out.native.0 test_files/out.native.1

rm --recursive --force test_files/rr-trace
test 0 ../result/bin/rr record --output-trace-dir=test_files/rr-trace ./test_files/test_determinism > test_files/out.rr.0
test 2 ../result/bin/rr replay test_files/rr-trace/ -- -batch -ex 'continue' -ex 'quit' > test_files/out.rr.1
echo "======  RR   ======"
../result/bin/icdiff --whole-file test_files/out.rr.0 test_files/out.rr.1
