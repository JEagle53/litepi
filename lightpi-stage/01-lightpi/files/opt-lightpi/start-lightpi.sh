#!/bin/sh
# Keeps the LightPi shell running; restarts it if it ever crashes.
export PYTHONUNBUFFERED=1
while true; do
    /usr/bin/python3 /opt/lightpi/lightpi.py >>"$HOME/lightpi.log" 2>&1
    sleep 2
done
