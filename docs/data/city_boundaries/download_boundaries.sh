#!/bin/bash
# Download full municipality boundary polygons from geoshape.ex.nii.ac.jp
# Run when server is available

OUTDIR="$(dirname "$0")"
BASE="https://geoshape.ex.nii.ac.jp/city/geojson/20240101"

curl -sL -o "$OUTDIR/13100_tokyo_wards_full.geojson" "$BASE/13/13100.geojson"
curl -sL -o "$OUTDIR/11203_kawaguchi_full.geojson" "$BASE/11/11203.geojson"
curl -sL -o "$OUTDIR/14100_yokohama.geojson" "$BASE/14/14100.geojson"
curl -sL -o "$OUTDIR/11100_saitama.geojson" "$BASE/11/11100.geojson"

echo "Downloaded boundary GeoJSON files."
