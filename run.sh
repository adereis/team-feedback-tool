#!/bin/bash
#
# Quick start script for Team Feedback Tool
# Works on macOS and Linux (including Fedora)
#

set -e

# Colors for output (if terminal supports it)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

echo ""
echo "=========================================="
echo "  Team Feedback Tool - Quick Start"
echo "=========================================="
echo ""

# Check for Python 3
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    # Check if 'python' is Python 3
    if python --version 2>&1 | grep -q "Python 3"; then
        PYTHON=python
    else
        echo -e "${RED}Error: Python 3 is required but not found.${NC}"
        echo "Please install Python 3.9 or later."
        exit 1
    fi
else
    echo -e "${RED}Error: Python is not installed.${NC}"
    echo "Please install Python 3.9 or later."
    exit 1
fi

# Check Python version (need 3.9+)
PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$($PYTHON -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$($PYTHON -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    echo -e "${RED}Error: Python 3.9+ is required. Found Python $PY_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found Python $PY_VERSION"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create virtual environment if it doesn't exist
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "Creating virtual environment (first run only)..."
    $PYTHON -m venv "$VENV_DIR"
    echo -e "${GREEN}✓${NC} Virtual environment created"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install/update dependencies if needed
if [ ! -f "$VENV_DIR/.deps_installed" ] || [ "requirements.txt" -nt "$VENV_DIR/.deps_installed" ]; then
    echo ""
    echo "Installing dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    touch "$VENV_DIR/.deps_installed"
    echo -e "${GREEN}✓${NC} Dependencies installed"
fi

# Determine the URL
HOST="127.0.0.1"
PORT="5001"
URL="http://${HOST}:${PORT}"

# Function to open browser (works on macOS and Linux)
open_browser() {
    sleep 1  # Give the server a moment to start
    if command -v open &> /dev/null; then
        # macOS
        open "$URL"
    elif command -v xdg-open &> /dev/null; then
        # Linux with desktop
        xdg-open "$URL" 2>/dev/null || true
    fi
}

echo ""
echo -e "${GREEN}Starting application...${NC}"
echo ""
echo "=========================================="
echo "  Open your browser to: $URL"
echo "  Press Ctrl+C to stop"
echo "=========================================="
echo ""

# Open browser in background
open_browser &

# Run the application
$PYTHON app.py
