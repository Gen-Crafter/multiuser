#!/bin/bash

# Wait for the desktop to be ready
sleep 10

# Start websockify for noVNC
websockify --web=/usr/share/novnc 6901 localhost:5900 &

# Open Firefox with LinkedIn login page
firefox --new-window https://www.linkedin.com/login &

exit 0
