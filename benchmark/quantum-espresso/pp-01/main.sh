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

pw.x < "$OUTPUT/si.scf.in"

pp.x < "$OUTPUT/si.pp_rho.in"

plotrho.x < "$OUTPUT/si.plotrho.in"

pp.x < "$OUTPUT/si.pp_rho_new.in"

"$gnuplot" "$OUTPUT/gnuplot1.in"

"$gnuplot" "$OUTPUT/gnuplot2.in"

# pw.x < "$OUTPUT/si.band.in"

# bands.x < "$OUTPUT/si.bands.in"

# plotband.x < "$OUTPUT/si.plotband.in"
