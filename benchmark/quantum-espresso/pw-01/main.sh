set -ex

cd "$(dirname -- "$0")"

TMP_DIR="$PWD/tmp"
PSEUDO_DIR="$(dirname "$PWD")/pseudo"

touch "$TMP_DIR"
rm -rf "$TMP_DIR"
mkdir --parents "$TMP_DIR"

for file in *.in; do
    sed "
            s:\$PSEUDO_DIR:$PSEUDO_DIR:g
            s:\$TMP_DIR:$TMP_DIR:g
        " "$file" > "$TMP_DIR/$(basename "$file")"
done


for diago in david cg ppcg ; do
    for el in si al cu ni; do
        echo "$el $diago"
        sed "s:\$diago:$diago:g" "$TMP_DIR/$el.scf.in" > "$TMP_DIR/$el.$diago.scf.in"
        pw.x < "$TMP_DIR/$el.$diago.scf.in"

        sed "s:\$diago:$diago:g" "$TMP_DIR/$el.band.in" > "$TMP_DIR/$el.$diago.band.in"
        pw.x < "$TMP_DIR/$el.$diago.band.in"
    done
done
