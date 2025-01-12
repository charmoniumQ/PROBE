set -ex

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

pw.x < "$TMP_DIR/si.scf.in"

pp.x < "$TMP_DIR/si.pp_rho.in"

plotrho.x < "$TMP_DIR/si.plotrho.in"

pp.x < "$TMP_DIR/si.pp_rho_new.in"

gnuplot "$TMP_DIR/gnuplot1.in"

gnuplot "$TMP_DIR/gnuplot2.in"

pw.x < "$TMP_DIR/si.band.in"

bands.x < "$TMP_DIR/si.bands.in"

plotband.x < "$TMP_DIR/si.plotband.in"
