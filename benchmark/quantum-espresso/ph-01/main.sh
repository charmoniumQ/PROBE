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

echo 'si.scf.in'
pw.x < "$OUTPUT/si.scf.in"

echo 'si.phG.in'
ph.x < "$OUTPUT/si.phG.in"

# echo 'si.phX.in'
# ph.x < "$OUTPUT/si.phX.in"

# echo 'si.scf.2.in'
# pw.x < "$OUTPUT/si.scf.2.in"

# echo 'si.phXsingle.in'
# ph.x < "$OUTPUT/si.phXsingle.in"

# echo 'c.scf.in'
# pw.x < "$OUTPUT/c.scf.in"

# echo 'c.phG.in'
# ph.x < "$OUTPUT/c.phG.in"

# echo 'ni.scf.in'
# pw.x < "$OUTPUT/ni.scf.in"

# echo 'ni.phX.in'
# ph.x < "$OUTPUT/ni.phX.in"
