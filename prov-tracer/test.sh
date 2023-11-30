cargo build
if [ ! -d tmp ]; then
    mkdir tmp
fi
env --chdir=tmp LD_PRELOAD=$PWD/target/debug/libprov_tracer.so python -c 'import os' &
pid=$!
wait
file=tmp/$pid.prov.trace
chmod 644 $file
cat $file
rm $file
