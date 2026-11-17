#!/bin/sh
# Build, sign (Developer ID), notarize and staple the macOS app, then zip it.
#
#   packaging/macos_release.sh            # build + sign + notarize -> dist/<zip>
#   packaging/macos_release.sh --upload   # ...and attach it to the GitHub release of the current version
#
# One-time setup (stores the notarization login in the keychain as "notary"):
#   xcrun notarytool store-credentials notary --apple-id <your Apple ID> --team-id <TEAM ID>
set -eu
cd "$(dirname "$0")/.."

APP="8BitDo Micro Remapper"
ZIP="8BitDo-Micro-Remapper-macOS-arm64.zip"
IDENTITY="${CODESIGN_IDENTITY:-$(security find-identity -v -p codesigning | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)}"
PROFILE="${NOTARY_PROFILE:-notary}"
VERSION="$(python3 -c 'import remapper; print(remapper.__version__)')"
PY="${PYTHON:-.venv/bin/python}"

[ -n "$IDENTITY" ] || { echo "No Developer ID Application certificate found" >&2; exit 1; }
echo "==> Building $APP $VERSION"
"$PY" -m PyInstaller --noconfirm --distpath dist --workpath build packaging/remapper.spec >/dev/null

echo "==> Signing with: $IDENTITY"
codesign --force --deep --options runtime --timestamp \
  --entitlements packaging/entitlements.plist --sign "$IDENTITY" "dist/$APP.app"
codesign --verify --deep --strict "dist/$APP.app"

echo "==> Notarizing (profile: $PROFILE)"
rm -f "dist/$ZIP"
ditto -c -k --sequesterRsrc --keepParent "dist/$APP.app" "dist/$ZIP"
xcrun notarytool submit "dist/$ZIP" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "dist/$APP.app"
spctl --assess --type execute --verbose "dist/$APP.app"

rm -f "dist/$ZIP"
ditto -c -k --sequesterRsrc --keepParent "dist/$APP.app" "dist/$ZIP"
echo "==> dist/$ZIP"

if [ "${1:-}" = "--upload" ]; then
  gh release upload "v$VERSION" "dist/$ZIP" --clobber
  echo "==> Uploaded to release v$VERSION"
fi
