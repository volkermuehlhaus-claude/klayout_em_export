#!/usr/bin/env bash
# Sparse checkout of the IHP-Open-PDK KLayout pcell libraries of SG13G2 and SG13CMOS5L into tests/pdk (Linux, or Git
# Bash on Windows).
# Usage: tests/setup_pdk.sh [commit-ish]   default: the commit the tests were last run with
# Only libs.tech/klayout/python, tech/*.lyp,*.lyt and the LVS deck tech/lvs (without its testing/) of each process are
# checked out. The submodules pycell4klayout-api and pypreprocessor are fetched at the commits the PDK pins.
# SG13CMOS5L's pcell code is SG13G2's: symlinks into ihp-sg13g2 of the same commit. Git for Windows writes a symlink
# as a text file with the target path; those are replaced by copies of their targets.
set -euo pipefail
cd "$(dirname "$0")"
REV="${1:-e73adb4045731ddec21634146d536380057f6a26}"
if [ -e pdk ]; then echo "tests/pdk exists, delete it first"; exit 1; fi

git clone --filter=blob:none --sparse --no-checkout https://github.com/IHP-GmbH/IHP-Open-PDK pdk
cd pdk
PATTERNS=()
for P in ihp-sg13g2 ihp-sg13cmos5l; do
    PATTERNS+=("/$P/libs.tech/klayout/python/" "/$P/libs.tech/klayout/tech/*.lyp" "/$P/libs.tech/klayout/tech/*.lyt"
               "/$P/libs.tech/klayout/tech/lvs/" "!/$P/libs.tech/klayout/tech/lvs/testing/")
done
MSYS_NO_PATHCONV=1 git sparse-checkout set --no-cone "${PATTERNS[@]}"
git checkout -q "$REV"
echo "PDK at $(git log --oneline -1)"

PY=ihp-sg13g2/libs.tech/klayout/python
P4K=$(git ls-tree HEAD "$PY/pycell4klayout-api" | awk '{print $3}')
PPP=$(git ls-tree HEAD "$PY/pypreprocessor" | awk '{print $3}')

fetch() {  # url commit target
    git init -q "$3"
    git -C "$3" fetch -q --depth 1 "$1" "$2"
    git -C "$3" checkout -q FETCH_HEAD
}
fetch https://github.com/IHP-GmbH/pycell4klayout-api "$P4K" ../_p4k
fetch https://github.com/IHP-GmbH/pypreprocessor "$PPP" ../_ppp
cp -r ../_p4k/source "$PY/pycell4klayout-api/"
mkdir -p "$PY/pypreprocessor"
cp -r ../_ppp/pypreprocessor "$PY/pypreprocessor/"
rm -rf ../_p4k ../_ppp
echo "pycell4klayout-api $P4K, pypreprocessor $PPP"

# SG13CMOS5L's symlinks (after the submodules: two of them point to their folders). A real symlink stays.
copied=0
while read -r link; do
    if [ -L "$link" ] || [ ! -f "$link" ]; then continue; fi
    target="$(dirname "$link")/$(cat "$link")"
    if [ ! -e "$target" ]; then continue; fi      # outside the checked-out parts
    rm -f "$link"
    cp -r "$target" "$link"
    copied=$((copied + 1))
done < <(git ls-files -s ihp-sg13cmos5l | awk '$1 == "120000" {print $4}')
echo "SG13CMOS5L: $copied symlink(s) replaced by copies"
