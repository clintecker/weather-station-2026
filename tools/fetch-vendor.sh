#!/bin/sh
# Fetch the exact pinned third-party sources used by firmware/ builds and C tests.
# Everything lands in vendor/ (git-ignored). Re-running verifies the pins.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cube="$root/vendor/STM32CubeWL"

CUBE_URL=https://github.com/STMicroelectronics/STM32CubeWL.git
CUBE_TAG=v1.6.0
CUBE_COMMIT=f934cd298bf82d45f96aac2f335c0bbd26d0b946
# path commit (must match the superproject's recorded submodule commits)
SUBMODULES="
Drivers/STM32WLxx_HAL_Driver 5c87cf00992c6e4ecf56c7c129b8dcfc6aa6f88e
Drivers/CMSIS/Device/ST/STM32WLxx 71a0b7860e700f7ca11afe4c4afd6cef684ad9bb
Drivers/BSP/STM32WLxx_Nucleo 90cb4924568890bce20cf5ed701f67486619cd6f
Middlewares/Third_Party/SubGHz_Phy 7dc059f353f359ec65c60a0549d53c1ebeaafa79
Middlewares/Third_Party/mbed-crypto 7ee7e20ec1460857446d2fa5628c1fd5ce6cd411
"

if [ ! -d "$cube/.git" ]; then
  git clone --depth 1 --branch "$CUBE_TAG" "$CUBE_URL" "$cube"
fi
actual=$(git -C "$cube" rev-parse HEAD)
[ "$actual" = "$CUBE_COMMIT" ] || { echo "STM32CubeWL is at $actual, expected $CUBE_COMMIT" >&2; exit 1; }

# The right commit is not enough: an edited or added file (a local experiment, a tampered cache)
# would still build. Fail on any change to the tracked tree.
clean() {
  changes=$(git -C "$1" status --porcelain --ignore-submodules=all)
  [ -z "$changes" ] || { printf '%s has local changes:\n%s\n' "$1" "$changes" >&2; exit 1; }
}
clean "$cube"

echo "$SUBMODULES" | while read -r path commit; do
  [ -n "$path" ] || continue
  git -C "$cube" submodule update --init --depth 1 "$path"
  actual=$(git -C "$cube/$path" rev-parse HEAD)
  [ "$actual" = "$commit" ] || { echo "$path is at $actual, expected $commit" >&2; exit 1; }
  clean "$cube/$path"
  echo "ok $path $commit"
done
echo "ok STM32CubeWL $CUBE_TAG $CUBE_COMMIT"
