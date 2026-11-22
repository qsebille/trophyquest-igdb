#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p out
archive="$PWD/out/screenshot-backfill.zip"
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
mkdir "$build_dir/files"

python -m pip install \
  --requirement requirements.txt \
  --target "$build_dir/files" \
  --platform manylinux_2_28_aarch64 \
  --platform manylinux2014_aarch64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-compile

cp -R src/igdb_enricher "$build_dir/files/"
(
  cd "$build_dir/files"
  zip -qr ../screenshot-backfill.zip . -x '*/__pycache__/*' '*.pyc'
)
mv "$build_dir/screenshot-backfill.zip" "$archive"
