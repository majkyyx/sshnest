#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/build_pyinstaller.sh

APPDIR="$ROOT_DIR/build/AppDir"
TOOLS_DIR="$ROOT_DIR/.tools"
APPIMAGE_TOOL="$TOOLS_DIR/appimagetool-x86_64.AppImage"

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -a "$ROOT_DIR/dist/SshNest" "$APPDIR/usr/bin/SshNest"
cp "$ROOT_DIR/sshnest.desktop" "$APPDIR/sshnest.desktop"
cp "$ROOT_DIR/sshnest.desktop" "$APPDIR/usr/share/applications/sshnest.desktop"
cp "$ROOT_DIR/assets/sshnest.svg" "$APPDIR/sshnest.svg"
cp "$ROOT_DIR/assets/sshnest.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/sshnest.svg"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/usr/bin/SshNest/SshNest" "$@"
EOF
chmod +x "$APPDIR/AppRun"

mkdir -p "$TOOLS_DIR"
if [[ ! -x "$APPIMAGE_TOOL" ]]; then
  curl -L \
    -o "$APPIMAGE_TOOL" \
    "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
  chmod +x "$APPIMAGE_TOOL"
fi

if "$APPIMAGE_TOOL" --version >/dev/null 2>&1; then
  ARCH=x86_64 "$APPIMAGE_TOOL" "$APPDIR" "$ROOT_DIR/SshNest-x86_64.AppImage"
else
  APPIMAGE_EXTRACT_AND_RUN=1 ARCH=x86_64 "$APPIMAGE_TOOL" "$APPDIR" "$ROOT_DIR/SshNest-x86_64.AppImage"
fi
