set -e -x

cargo build
if [ ! -d tmp ]; then
    mkdir tmp
fi

cmd="head ../Cargo.toml"
env --chdir=tmp RUST_BACKTRACE=1 LD_PRELOAD=$PWD/target/debug/libtestf.so sh -c "$cmd" &
# env --chdir=tmp RUST_BACKTRACE=1 LD_PRELOAD=$PWD/target/debug/libtestf.so $PWD/target/debug/exe $cmd &
wait $!
