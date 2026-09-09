#!/usr/bin/env bash
# Build the Dia Gold CRM desktop app on macOS or Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller

rm -rf build dist
pyinstaller packaging/DiaGoldCRM.spec --noconfirm

if [[ "$(uname)" == "Darwin" ]]; then
  cd dist
  ditto -c -k --sequesterRsrc --keepParent DiaGoldCRM.app "DiaGoldCRM-macOS-$(uname -m).zip"
  echo "Built: dist/DiaGoldCRM-macOS-$(uname -m).zip"
else
  echo "Built: dist/DiaGoldCRM/"
fi
