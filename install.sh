#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/oracle-auto-create-adapted}"

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip

mkdir -p "$PROJECT_DIR"
echo "Dependencies installed. Clone/copy the repo into: $PROJECT_DIR"
echo "Then run: cd $PROJECT_DIR && bash setup.sh"
