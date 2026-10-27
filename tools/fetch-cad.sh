#!/bin/sh
# Fetch the manufacturers' 3D models of board B's parts (hardware/bench-breadboard-r0, renders/3d-*)
# into vendor/cad (git-ignored), pinned by SHA-256. Re-running verifies the pins. Without them,
# make.py draws plain boxes in their place.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
dir="$root/vendor/cad"
mkdir -p "$dir"
ADA=https://raw.githubusercontent.com/adafruit/Adafruit_CAD_Parts/c128bceb1f96b6ea8b68f250bda986ba85da24ea

fetch() {   # name url sha256
  if [ -f "$dir/$1" ]; then   # already fetched: verify the pin again
    sum=$(shasum -a 256 "$dir/$1" | awk '{print $1}')
    [ "$sum" = "$3" ] || { echo "$1 has SHA-256 $sum, expected $3: delete it and re-run" >&2; exit 1; }
    return 0
  fi
  curl -fsSL -o "$dir/$1.part" "$2"
  sum=$(shasum -a 256 "$dir/$1.part" | awk '{print $1}')
  if [ "$sum" != "$3" ]; then   # never install a file that fails its pin: make.py would use it
    rm -f "$dir/$1.part"
    echo "$1 downloaded with SHA-256 $sum, expected $3: not installed" >&2
    exit 1
  fi
  mv "$dir/$1.part" "$dir/$1"
}

fetch chgr-4755.step "$ADA/4755%20USB%20Solar%20Charger/4755%20USB%20Solar%20Charger.step" \
  e39c1d23f4b661e9c1c3ad994fc4d093521475910f59cfbdbf1abb7db8ed026f
fetch ina-5832.step "$ADA/5832%20INA228%20STEMMA%20QT/5832%20INA228%20STEMMA%20QT.step" \
  701a1218ebb487fcea3885c3fbee4d62b44c5e3f696c0d88083ee149094fb82b
fetch gauge-5580.step "$ADA/5580%20MAX17048/5580%20MAX17048.step" \
  acc003d40a01eeeb7e5f63c9f6da4e4e87a5113dcc4a02990f2f26b7df2e7971
fetch cell-353.step "$ADA/353%206600mAh%20Battery/353%206600mAh%20Battery.step" \
  7338c3ed19ce7ff18f6a83ee874a57777a0679fbea3b6a8fac394cfd52a8c23f
fetch reg-2122.step https://www.pololu.com/file/0J1374/pololu-step-up-step-down-voltage-regulator-s7v8fx.step \
  1bdaa13a7e0b634f9f4bb45f22c088f3b8e8441d8b0866a5b7e670253c667e4e
echo "ok vendor/cad: 5 models"
