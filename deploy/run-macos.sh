#!/bin/sh
# launchd supplies absolute checkout and configuration paths as arguments.
set -eu

project_dir=$1
env_file=$2
shift 2

if [ ! -f "$env_file" ]; then
    printf 'Missing configuration file: %s\n' "$env_file" >&2
    exit 1
fi

# This is a trusted, user-owned shell configuration file.
set -a
. "$env_file"
set +a

cd "$project_dir"
exec "$project_dir/.venv/bin/mutc-tracker" "$@"
