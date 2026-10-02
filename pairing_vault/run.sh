#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
bashio::log.info "Starting Pairing Vault"
export DATA_DIR=/data
export PORT=8099
# Home Assistant's Ingress proxy
export ALLOWED_CLIENTS=172.30.32.2
cd /opt/pairing_vault || exit 1
exec python3 -m app
