#!/bin/bash
pip install -r requirements.txt
apt-get update -qq && apt-get install -y -qq fonts-liberation ffmpeg 2>/dev/null || true
