#!/usr/bin/env sh
# Integration fragment for a serialized deployment initializer, NOT a web entrypoint.
# Invoke with sh; no executable-bit requirement after extracting a ZIP.
set -eu
: "${REVOLUT_SITE:?Set REVOLUT_SITE to the existing site folder name}"
case "$REVOLUT_SITE" in
  -*|.*|*[!a-zA-Z0-9._-]*) echo 'Invalid site folder name' >&2; exit 2 ;;
esac
cd /home/frappe/frappe-bench
# Explicit import is required before the app is in the site's installed-app list.
# This is a constant CLI expression: no user input is evaluated as Python code.
bench --site "$REVOLUT_SITE" execute "__import__('revolut_bank_feed.deployment', fromlist=['ensure_installed']).ensure_installed()"
# Your existing migration job can perform this instead, avoiding duplicate migration.
if [ "${REVOLUT_RUN_MIGRATE:-1}" = '1' ]; then
  bench --site "$REVOLUT_SITE" migrate
fi
# Preserve the existing site's scheduler policy unless explicitly configured otherwise.
if [ "${REVOLUT_ENABLE_SCHEDULER:-0}" = '1' ]; then
  bench --site "$REVOLUT_SITE" enable-scheduler
fi
