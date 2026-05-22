#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  12_autostart.sh
#  Sets up the unified smart home engine to start automatically
#  every time Ubuntu boots — no manual intervention needed.
#
#  Usage:
#    bash 12_autostart.sh          install autostart
#    bash 12_autostart.sh remove   remove autostart
# ─────────────────────────────────────────────────────────────────

PROJECT_DIR="$HOME/Desktop/smarthome_analysis"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
SCRIPT="$PROJECT_DIR/11_unified_engine.py"
LOG="$PROJECT_DIR/output/unified_alerts.log"
SERVICE_NAME="smarthome-engine"
SERVICE_FILE="$HOME/.config/systemd/user/$SERVICE_NAME.service"

if [ "$1" == "remove" ]; then
    echo "Removing autostart..."
    systemctl --user stop  $SERVICE_NAME 2>/dev/null
    systemctl --user disable $SERVICE_NAME 2>/dev/null
    rm -f "$SERVICE_FILE"
    systemctl --user daemon-reload
    echo "Done — autostart removed."
    exit 0
fi

# ── Validate project exists ──────────────────────────────────────
if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found."
    echo "Make sure 11_unified_engine.py is in $PROJECT_DIR"
    exit 1
fi
if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: venv not found at $VENV_PYTHON"
    echo "Run: cd $PROJECT_DIR && python -m venv venv && pip install -r requirements.txt"
    exit 1
fi

# ── Create systemd user service ──────────────────────────────────
mkdir -p "$HOME/.config/systemd/user"

cat > "$SERVICE_FILE" << SERVICE
[Unit]
Description=Smart Home Behaviour Engine
After=network.target

[Service]
Type=simple
ExecStart=$VENV_PYTHON $SCRIPT
WorkingDirectory=$PROJECT_DIR
Restart=always
RestartSec=10
StandardOutput=append:$LOG
StandardError=append:$LOG

[Install]
WantedBy=default.target
SERVICE

# ── Enable and start ─────────────────────────────────────────────
systemctl --user daemon-reload
systemctl --user enable $SERVICE_NAME
systemctl --user start  $SERVICE_NAME

echo ""
echo "================================================"
echo "  Smart Home Engine — AUTOSTART INSTALLED"
echo "================================================"
echo ""
echo "  Status  : $(systemctl --user is-active $SERVICE_NAME)"
echo "  Log     : $LOG"
echo ""
echo "  Useful commands:"
echo "  systemctl --user status  $SERVICE_NAME   (check status)"
echo "  systemctl --user stop    $SERVICE_NAME   (stop)"
echo "  systemctl --user start   $SERVICE_NAME   (start)"
echo "  systemctl --user restart $SERVICE_NAME   (restart)"
echo "  tail -f $LOG             (watch live)"
echo ""
echo "  To remove: bash 12_autostart.sh remove"