#!/bin/bash

echo "Starting V2Ray Proxy Tester..."
echo ""
echo "Web interface will be available at: http://localhost:5000"
echo "Press Ctrl+C to stop the server"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH"
    echo "Please install Python 3.7 or higher"
    exit 1
fi

# Install required packages
echo "Installing required packages..."
pip3 install flask flask-socketio requests

# Create necessary directories
mkdir -p results logs uploads

# Start the application
echo "Starting Flask application..."
python3 app.py
