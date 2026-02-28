#!/bin/bash
set -e

# RaccBuddy Restore Script
# Restores database and WhatsApp session from backup on Umbrel or other systems

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== RaccBuddy Restore Script ===${NC}"
echo ""

# Check if backup directory is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Backup directory not provided${NC}"
    echo -e "${YELLOW}Usage: ./restore-from-backup.sh <backup-directory>${NC}"
    echo -e "${YELLOW}Example: ./restore-from-backup.sh ./backups/20260223_120000${NC}"
    exit 1
fi

BACKUP_DIR="$1"

# Verify backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Backup directory not found: ${BACKUP_DIR}${NC}"
    exit 1
fi

echo -e "${YELLOW}Backup directory: ${BACKUP_DIR}${NC}"
echo ""

# Step 1: Check if containers are running
echo -e "${GREEN}=== Checking Docker containers ===${NC}"
if ! docker compose ps db | grep -q "Up"; then
    echo -e "${YELLOW}Starting containers...${NC}"
    docker compose up -d db
    echo -e "${YELLOW}Waiting for database to be ready...${NC}"
    sleep 10
fi
echo -e "${GREEN}✓ Containers are running${NC}"
echo ""

# Step 2: Restore database
if [ -f "${BACKUP_DIR}/database.sql.gz" ]; then
    echo -e "${GREEN}=== Restoring database ===${NC}"
    echo -e "${YELLOW}This will overwrite the current database. Continue? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        gunzip -c "${BACKUP_DIR}/database.sql.gz" | docker compose exec -T db psql -U raccbuddy raccbuddy
        echo -e "${GREEN}✓ Database restored successfully${NC}"
    else
        echo -e "${YELLOW}Skipping database restore${NC}"
    fi
elif [ -f "${BACKUP_DIR}/database.sql" ]; then
    echo -e "${GREEN}=== Restoring database ===${NC}"
    echo -e "${YELLOW}This will overwrite the current database. Continue? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        cat "${BACKUP_DIR}/database.sql" | docker compose exec -T db psql -U raccbuddy raccbuddy
        echo -e "${GREEN}✓ Database restored successfully${NC}"
    else
        echo -e "${YELLOW}Skipping database restore${NC}"
    fi
else
    echo -e "${RED}Warning: No database backup found (database.sql or database.sql.gz)${NC}"
fi
echo ""

# Step 3: Restore WhatsApp session
if [ -f "${BACKUP_DIR}/whatsapp-session.tar.gz" ]; then
    echo -e "${GREEN}=== Restoring WhatsApp session ===${NC}"
    echo -e "${YELLOW}This will restore your WhatsApp session (no need to re-scan QR code). Continue? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        # Stop whatsapp service during restore
        docker compose stop whatsapp || true

        # Restore the volume
        docker run --rm \
            -v raccbuddy_wa-session:/data \
            -v "$(realpath ${BACKUP_DIR})":/backup \
            alpine \
            sh -c "rm -rf /data/* && cd /data && tar xzf /backup/whatsapp-session.tar.gz"

        echo -e "${GREEN}✓ WhatsApp session restored successfully${NC}"

        # Restart whatsapp service
        docker compose up -d whatsapp
        echo -e "${GREEN}✓ WhatsApp service restarted${NC}"
    else
        echo -e "${YELLOW}Skipping WhatsApp session restore${NC}"
    fi
else
    echo -e "${RED}Warning: No WhatsApp session backup found (whatsapp-session.tar.gz)${NC}"
fi
echo ""

# Step 4: Restart all services
echo -e "${GREEN}=== Restarting all services ===${NC}"
docker compose up -d
echo -e "${GREEN}✓ All services restarted${NC}"
echo ""

# Summary
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           🦝 Restore Complete! 🦝                          ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Check the logs to ensure everything is working:${NC}"
echo -e "  ${YELLOW}docker compose logs -f${NC}"
echo ""
echo -e "${GREEN}Your RaccBuddy is ready to go! 🚀${NC}"
