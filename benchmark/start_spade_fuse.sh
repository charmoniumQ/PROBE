#!./result/bin/bash
set -e -x
./result/bin/spade start

./result/bin/spade control <<EOF
add reporter LinuxFUSE $PWD/test
add storage Neo4j
add analyzer CommandLine
EOF

./result/bin/env --chdir=$PWD/test/$PWD ./build.sh

rm --force prov.dot

./result/bin/spade query <<EOF
set storage Neo4j
$graph = $base.getLineage($base.getVertex("filename" == 'build.sh'), 100, 'both')
export > $PWD/prov.dot
dump all $graph
EOF

# ./result/bin/spade control <<EOF
# remove reporter LinuxFUSE
# remove storage Neo4j
# remove analyzer CommandLine
# EOF

# ./result/bin/xdot prov.dot
