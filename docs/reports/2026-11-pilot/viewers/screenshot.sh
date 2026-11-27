#!/bin/bash
# Task 21 Step 7: screenshot a waveform viewer on a virtual display.
#
#   xvfb-run -a -s "-screen 0 1600x900x24" docs/reports/2026-11-pilot/viewers/screenshot.sh gtkwave WAVE.fst WAVE.gtkw OUT.png
#   xvfb-run -a -s "-screen 0 1600x900x24" docs/reports/2026-11-pilot/viewers/screenshot.sh surfer WAVE.fst WAVE.sucl OUT.png
#
# Starts the viewer with the save file vgacap-export wrote, waits WAIT seconds (default 20) for it
# to load and draw, captures the whole screen with ImageMagick's import, and stops the viewer.
set -eu
viewer=$1 wave=$2 save=$3 out=$4
case $viewer in
  gtkwave) /usr/bin/gtkwave "$wave" "$save" & ;;
  surfer) /usr/local/bin/surfer "$wave" --command-file "$save" & ;;
  *) echo "screenshot.sh: viewer must be gtkwave or surfer" >&2; exit 2 ;;
esac
pid=$!
sleep "${WAIT:-20}"
if ! kill -0 "$pid"; then
  echo "screenshot.sh: $viewer exited before the screenshot" >&2
  exit 1
fi
import -window root "$out"
kill "$pid"
wait "$pid" || true
