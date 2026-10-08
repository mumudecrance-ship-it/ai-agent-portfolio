#!/bin/zsh
set -eu

cd -- "$(dirname -- "$0")"

python3 server.py --port 8927 &
event_server_pid=$!

cleanup() {
  kill "$event_server_pid" 2>/dev/null || true
}

trap cleanup EXIT INT TERM
sleep 1
open "http://127.0.0.1:8927"
wait "$event_server_pid"
