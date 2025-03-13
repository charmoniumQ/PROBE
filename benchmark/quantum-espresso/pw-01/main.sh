set -ex

ROOT="$(dirname -- "$0")"

OUTPUT="${OUTPUT-$PWD/tmp}"
PSEUDO_DIR="$(dirname -- "$ROOT")/pseudo"

mkdir --parents "$OUTPUT"

for file in "$ROOT"/*.in; do
    sed "
            s:\$PSEUDO_DIR:$PSEUDO_DIR:g
            s:\$TMP_DIR:$OUTPUT:g
        " "$file" > "$OUTPUT/$(basename "$file")"
done


# for diago in david cg ppcg ; do
#     for el in si al cu ni; do
for diago in david ; do
    for el in si ; do
        echo "$el $diago"
        sed "s:\$diago:$diago:g" "$OUTPUT/$el.scf.in" > "$OUTPUT/$el.$diago.scf.in"
        pw.x < "$OUTPUT/$el.$diago.scf.in"

        sed "s:\$diago:$diago:g" "$OUTPUT/$el.band.in" > "$OUTPUT/$el.$diago.band.in"
        pw.x < "$OUTPUT/$el.$diago.band.in"
    done
done
