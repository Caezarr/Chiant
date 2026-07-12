#!/usr/bin/env sh
set -eu

if command -v nmcli >/dev/null 2>&1; then
  nmcli networking off || true
  sleep 2
  nmcli networking on
  exit 0
fi

if command -v rfkill >/dev/null 2>&1; then
  rfkill unblock wifi
fi

exit 1
