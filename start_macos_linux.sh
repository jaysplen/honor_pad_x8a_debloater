#!/bin/sh
script_dir=$(dirname "$0") || exit 1
exec python3 "$script_dir/honor_x8a_debloater.py" "$@"
