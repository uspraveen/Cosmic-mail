#!/usr/bin/env bash
# deploy.sh — build + push Cosmic Mail to EC2
# Usage:  bash scripts/deploy.sh [ec2-user@HOST] [/path/to/key.pem]
set -euo pipefail

HOST="${1:-ec2-user@3.144.41.242}"
KEY="${2:-$HOME/Downloads/cosmic-vpc-feb-2026.pem}"
SSH="ssh -i $KEY -o StrictHostKeyChecking=no"
SCP="scp -i $KEY -o StrictHostKeyChecking=no"
REMOTE_DIR="/opt/cosmic-mail"

echo "=== Packaging source ==="
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

tar --exclude='.git' \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache' \
    --exclude='.pytest_tmp' \
    --exclude='manual_test*.db' \
    --exclude='scripts/deploy.sh' \
    -czf /tmp/cosmic-mail-deploy.tgz .

echo "=== Uploading to $HOST ==="
$SCP /tmp/cosmic-mail-deploy.tgz "$HOST:/tmp/cosmic-mail-deploy.tgz"

echo "=== Deploying on server ==="
$SSH "$HOST" bash -s <<'REMOTE'
set -euo pipefail
REMOTE_DIR="/opt/cosmic-mail"
sudo mkdir -p "$REMOTE_DIR"
cd "$REMOTE_DIR"

echo "--- Extracting ---"
sudo tar -xzf /tmp/cosmic-mail-deploy.tgz -C "$REMOTE_DIR"

echo "--- Updating .env: fix hostname ---"
ENV_FILE="$REMOTE_DIR/infra/.env"
# Update public mail hostname to proper domain
sudo sed -i 's|^COSMIC_MAIL_PUBLIC_MAIL_HOSTNAME=.*|COSMIC_MAIL_PUBLIC_MAIL_HOSTNAME=mail.thelearnchain.com|' "$ENV_FILE"
# Ensure no duplicate COSMIC_MAIL_ADMIN_API_KEY lines
sudo awk '!seen[$0]++' "$ENV_FILE" | sudo tee "$ENV_FILE.tmp" > /dev/null && sudo mv "$ENV_FILE.tmp" "$ENV_FILE"

echo "--- Rebuilding Docker image ---"
cd "$REMOTE_DIR/infra"
sudo docker compose -f docker-compose.production.yml build cosmic-mail

echo "--- Restarting services ---"
sudo docker compose -f docker-compose.production.yml up -d --no-deps cosmic-mail

echo "--- Restarting James to pick up hostname ---"
sudo docker compose -f docker-compose.production.yml restart james

echo "--- Waiting for health check ---"
sleep 15
sudo docker compose -f docker-compose.production.yml ps

echo "=== Deploy complete ==="
REMOTE

echo "=== Done. ==="
echo ""
echo "IMPORTANT — DNS change required to fix SPF alignment:"
echo "  Update TXT record for: mail.thelearnchain.com"
echo "  Old value: v=spf1 mx -all"
echo "  New value: v=spf1 mx include:amazonses.com -all"
echo ""
echo "  (Google Cloud DNS → Zone: thelearnchain-com → mail.thelearnchain.com TXT)"
