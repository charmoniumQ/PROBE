set -e -x

gcc -Wall -shared -fPIC -o libtesth.so lib.c
env LD_PRELOAD=$PWD/libtesth.so sh -c "head test.sh test.sh"
