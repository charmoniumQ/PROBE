set -ex

cd "$(dirname -- "$0")"

TMP_DIR="$PWD/tmp"
PSEUDO_DIR="$(dirname -- "$PWD")/pseudo"

touch "$TMP_DIR"
rm -rf "$TMP_DIR"
mkdir --parents "$TMP_DIR"

for file in *.in; do
    sed "
            s:\$PSEUDO_DIR:$PSEUDO_DIR:g
            s:\$TMP_DIR:$TMP_DIR:g
        " "$file" > "$TMP_DIR/$(basename "$file")"
done

echo 'si.scf.in'
pw.x < "$TMP_DIR/si.scf.in"

echo 'si.phG.in'
ph.x < "$TMP_DIR/si.phG.in"

echo 'si.phX.in'
ph.x < "$TMP_DIR/si.phX.in"

# echo 'si.scf.2.in'
# pw.x < "$TMP_DIR/si.scf.2.in"

# echo 'si.phXsingle.in'
# ph.x < "$TMP_DIR/si.phXsingle.in"

# echo 'c.scf.in'
# pw.x < "$TMP_DIR/c.scf.in"

# echo 'c.phG.in'
# ph.x < "$TMP_DIR/c.phG.in"

# echo 'ni.scf.in'
# pw.x < "$TMP_DIR/ni.scf.in"

# echo 'ni.phX.in'
# ph.x < "$TMP_DIR/ni.phX.in"
