#!/bin/bash

APP_NAME="SecureLoader"

echo "==== Uninstall $APP_NAME ===="
echo ""
echo "Which installation type do you want to remove?"
echo "  1) System-wide  (/opt, requires sudo)"
echo "  2) Local        (~/.local, current user only)"
read -r -p "Choose [1/2]: " CHOICE

if [ "$CHOICE" = "1" ]; then
    INSTALL_DIR="/opt/$APP_NAME"
    BIN_LINK="/usr/local/bin/$APP_NAME"
    ICON_DEST="/usr/share/pixmaps/${APP_NAME}.png"
    DESKTOP_DEST="/usr/share/applications/${APP_NAME}.desktop"

    sudo rm -rf "$INSTALL_DIR"
    sudo rm -f  "$BIN_LINK"
    sudo rm -f  "$ICON_DEST"
    sudo rm -f  "$DESKTOP_DEST"

    echo ""
    echo "Removed: $INSTALL_DIR"
    echo "Removed: $BIN_LINK"
    echo "Removed: $ICON_DEST"
    echo "Removed: $DESKTOP_DEST"

elif [ "$CHOICE" = "2" ]; then
    INSTALL_DIR="$HOME/.local/bin"
    ICON_DEST="$HOME/.local/share/icons/${APP_NAME}.png"
    DESKTOP_DEST="$HOME/.local/share/applications/${APP_NAME}.desktop"

    rm -f "$INSTALL_DIR/$APP_NAME"
    rm -f "$ICON_DEST"
    rm -f "$DESKTOP_DEST"

    echo ""
    echo "Removed: $INSTALL_DIR/$APP_NAME"
    echo "Removed: $ICON_DEST"
    echo "Removed: $DESKTOP_DEST"

else
    echo "Invalid choice. Exiting."
    exit 1
fi

echo ""
echo "$APP_NAME uninstalled successfully."
