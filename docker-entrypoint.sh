#!/bin/sh
# Docker entrypoint script for RaccBuddy
# Runs database migrations before starting the application

set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting RaccBuddy application..."
exec python -m src.bot
