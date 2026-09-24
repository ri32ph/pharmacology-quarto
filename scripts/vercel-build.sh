#!/usr/bin/env bash
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"

if python3 scripts/sync-notion-course.py --activate; then
  echo "Using Notion-generated lecture 03 content."
else
  echo "Notion sync failed; rendering the committed Quarto fallback." >&2
fi

if command -v quarto >/dev/null 2>&1; then
  quarto_bin=$(command -v quarto)
else
  quarto_version=1.10.18
  quarto_dir="/tmp/quarto-${quarto_version}"
  archive="/tmp/quarto-${quarto_version}-linux-amd64.tar.gz"
  curl -fsSL "https://github.com/quarto-dev/quarto-cli/releases/download/v${quarto_version}/quarto-${quarto_version}-linux-amd64.tar.gz" -o "$archive"
  mkdir -p "$quarto_dir"
  tar -xzf "$archive" -C "$quarto_dir" --strip-components=1
  quarto_bin="$quarto_dir/bin/quarto"
fi

"$quarto_bin" render
