#!/bin/bash
set -e

APP_NAME="SecureLoader"
SPEC="SecureLoader.spec"
ICON_SRC="../src/secure_loader/gui/resources/icons/icon.png"
DIST_DIR="./dist"
VENV_DIR="../.venv"

# ------------------------------------------------------------------ build

echo "==== [1/4] Cleaning previous build ===="
rm -rf ./dist ./out __pycache__

echo ""
echo "==== [2/4] Setting up virtual environment ===="
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

echo ""
echo "==== [3/4] Installing dependencies ===="
pip install -e "../[gui,build]"

echo ""
echo "==== [4/4] Building executable ===="
pyinstaller "$SPEC"

deactivate

EXE="$(realpath "$DIST_DIR/$APP_NAME")"

# ------------------------------------------------------------------ install target

echo ""
echo "Install location:"
echo "  1) User-local   (~/.local        — no sudo required)"
echo "  2) System-wide  (/opt            — requires sudo)"
read -rp "Choice [1/2, default 1]: " CHOICE

if [[ "$CHOICE" == "2" ]]; then
    APP_DIR="/opt/$APP_NAME"
    BIN_DIR="/usr/local/bin"
    DESKTOP_DIR="/usr/share/applications"
    ICON_DIR="/usr/share/icons/hicolor/256x256/apps"
    SUDO="sudo"
else
    APP_DIR="$HOME/.local/share/$APP_NAME"
    BIN_DIR="$HOME/.local/bin"
    DESKTOP_DIR="$HOME/.local/share/applications"
    ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
    SUDO=""
fi

# ------------------------------------------------------------------ install

echo ""
echo "Installing to $APP_DIR ..."

$SUDO mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

$SUDO cp "$EXE"      "$APP_DIR/$APP_NAME"
$SUDO cp "$ICON_SRC" "$APP_DIR/icon.png"
$SUDO cp "$ICON_SRC" "$ICON_DIR/$APP_NAME.png"
$SUDO chmod +x "$APP_DIR/$APP_NAME"

# Symlink into bin
$SUDO ln -sf "$APP_DIR/$APP_NAME" "$BIN_DIR/$APP_NAME"

# Write .desktop file
$SUDO tee "$DESKTOP_DIR/$APP_NAME.desktop" > /dev/null <<EOF
[Desktop Entry]
Type=Application
Name=SecureLoader
GenericName=Firmware Updater
Comment=Upload encrypted .bin firmware to embedded devices over serial
Exec=$APP_DIR/$APP_NAME
Icon=$ICON_DIR/$APP_NAME.png
Terminal=false
Categories=Development;Embedded;
EOF

$SUDO chmod +x "$DESKTOP_DIR/$APP_NAME.desktop"

# Refresh icon and desktop caches (best-effort)
${SUDO} gtk-update-icon-cache    "${ICON_DIR%/256x256/apps}" 2>/dev/null || true
${SUDO} update-desktop-database  "$DESKTOP_DIR"              2>/dev/null || true

echo ""
echo "Done."
echo "  App folder : $APP_DIR"
echo "  Executable : $BIN_DIR/$APP_NAME  (symlink)"
echo "  Menu entry : $DESKTOP_DIR/$APP_NAME.desktop"
