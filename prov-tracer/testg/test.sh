set -e -x

cargo build
if [ ! -d tmp ]; then
    mkdir tmp
fi

cmd="head --lines=0 ../Cargo.toml ../Cargo.lock ../test.sh"
env --chdir=tmp RUST_BACKTRACE=1 LD_PRELOAD=$PWD/target/debug/libtestf.so sh -c "$cmd" &
# env --chdir=tmp RUST_BACKTRACE=1 LD_PRELOAD=$PWD/target/debug/libtestf.so $PWD/target/debug/exe $cmd &
wait $!
