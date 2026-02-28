#!/bin/bash
set -e

# RaccBuddy Deployment Script
# Builds multi-platform images, pushes to Docker Hub, and backs up data

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DOCKER_USERNAME="${DOCKER_USERNAME:-}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
PLATFORMS="linux/amd64,linux/arm64"

# Image names
APP_IMAGE="raccbuddy-app"
WHATSAPP_IMAGE="raccbuddy-whatsapp"

echo -e "${GREEN}=== RaccBuddy Docker Hub Deployment ===${NC}"
echo ""

# Step 1: Verify Docker Hub credentials
if [ -z "$DOCKER_USERNAME" ]; then
    echo -e "${YELLOW}Enter your Docker Hub username:${NC}"
    read DOCKER_USERNAME
fi

if [ -z "$DOCKER_USERNAME" ]; then
    echo -e "${RED}Error: Docker Hub username is required${NC}"
    exit 1
fi

echo -e "${GREEN}Docker Hub username: ${DOCKER_USERNAME}${NC}"
echo ""

# Step 2: Login to Docker Hub
echo -e "${YELLOW}Logging in to Docker Hub...${NC}"
docker login
echo ""

# Step 3: Create buildx builder if it doesn't exist
echo -e "${YELLOW}Setting up Docker buildx for multi-platform builds...${NC}"
if ! docker buildx inspect raccbuddy-builder > /dev/null 2>&1; then
    docker buildx create --name raccbuddy-builder --use
else
    docker buildx use raccbuddy-builder
fi
docker buildx inspect --bootstrap
echo ""

# Step 4: Build and push main app image
echo -e "${GREEN}=== Building and pushing main app image ===${NC}"
echo -e "${YELLOW}Platforms: ${PLATFORMS}${NC}"
echo -e "${YELLOW}Image: ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG}${NC}"
docker buildx build --platform ${PLATFORMS} \
    -t ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG} \
    -t ${DOCKER_USERNAME}/${APP_IMAGE}:latest \
    --push \
    -f Dockerfile \
    .
echo -e "${GREEN}✓ Main app image built and pushed${NC}"
echo ""

# Step 5: Build and push WhatsApp service image
echo -e "${GREEN}=== Building and pushing WhatsApp service image ===${NC}"
echo -e "${YELLOW}Platforms: ${PLATFORMS}${NC}"
echo -e "${YELLOW}Image: ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG}${NC}"
docker buildx build --platform ${PLATFORMS} \
    -t ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG} \
    -t ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:latest \
    --push \
    -f whatsapp-service/Dockerfile \
    whatsapp-service/
echo -e "${GREEN}✓ WhatsApp service image built and pushed${NC}"
echo ""

# Step 6: Create backup directory
echo -e "${GREEN}=== Creating backup directory ===${NC}"
mkdir -p "$BACKUP_DIR"
echo -e "${YELLOW}Backup location: ${BACKUP_DIR}${NC}"
echo ""

# Step 7: Dump PostgreSQL database
echo -e "${GREEN}=== Dumping PostgreSQL database ===${NC}"
if docker compose ps db | grep -q "Up"; then
    echo -e "${YELLOW}Dumping database from running container...${NC}"
    docker compose exec -T db pg_dump -U raccbuddy raccbuddy > "${BACKUP_DIR}/database.sql"
    echo -e "${GREEN}✓ Database dumped to ${BACKUP_DIR}/database.sql${NC}"

    # Create a compressed version
    gzip -c "${BACKUP_DIR}/database.sql" > "${BACKUP_DIR}/database.sql.gz"
    echo -e "${GREEN}✓ Compressed backup created: ${BACKUP_DIR}/database.sql.gz${NC}"
else
    echo -e "${RED}Warning: Database container is not running. Skipping database dump.${NC}"
    echo -e "${YELLOW}Start the containers with 'docker compose up -d' first.${NC}"
fi
echo ""

# Step 8: Backup WhatsApp session volume
echo -e "${GREEN}=== Backing up WhatsApp session data ===${NC}"
if docker volume ls | grep -q "raccbuddy_wa-session"; then
    echo -e "${YELLOW}Backing up WhatsApp session volume...${NC}"

    # Create a temporary container to copy data from volume
    docker run --rm \
        -v raccbuddy_wa-session:/data \
        -v "$(pwd)/${BACKUP_DIR}":/backup \
        alpine \
        sh -c "cd /data && tar czf /backup/whatsapp-session.tar.gz ."

    echo -e "${GREEN}✓ WhatsApp session backed up to ${BACKUP_DIR}/whatsapp-session.tar.gz${NC}"
else
    echo -e "${RED}Warning: WhatsApp session volume not found. Skipping backup.${NC}"
    echo -e "${YELLOW}The volume will be created on first run.${NC}"
fi
echo ""

# Step 9: Create a deployment info file
echo -e "${GREEN}=== Creating deployment info ===${NC}"
cat > "${BACKUP_DIR}/deployment-info.txt" << EOF
RaccBuddy Deployment Information
Generated: $(date)

Docker Hub Images:
- App: ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG}
- WhatsApp: ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG}

Platforms: ${PLATFORMS}

To restore on Umbrel or another system:
1. Pull images:
   docker pull ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG}
   docker pull ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG}

2. Restore database:
   gunzip -c database.sql.gz | docker compose exec -T db psql -U raccbuddy raccbuddy

3. Restore WhatsApp session:
   docker run --rm -v raccbuddy_wa-session:/data -v \$(pwd):/backup alpine sh -c "cd /data && tar xzf /backup/whatsapp-session.tar.gz"

4. Update docker-compose.yml to use your images:
   Replace 'build: .' with 'image: ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG}'
   Replace 'build: ./whatsapp-service' with 'image: ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG}'
EOF
echo -e "${GREEN}✓ Deployment info saved to ${BACKUP_DIR}/deployment-info.txt${NC}"
echo ""

# Step 10: Create docker-compose.yml for deployment
echo -e "${GREEN}=== Creating deployment docker-compose.yml ===${NC}"
cat > "${BACKUP_DIR}/docker-compose.yml" << EOF
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: raccbuddy
      POSTGRES_PASSWORD: raccbuddy
      POSTGRES_DB: raccbuddy
    volumes:
      - pgdata:/var/lib/postgresql/data
    restart: unless-stopped

  app:
    image: ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG}
    environment:
      # Required: Set your Telegram bot token
      - TELEGRAM_BOT_TOKEN=\${TELEGRAM_BOT_TOKEN}
      - OWNER_TELEGRAM_ID=\${OWNER_TELEGRAM_ID:-0}

      # WhatsApp
      - OWNER_WHATSAPP_NUMBER=\${OWNER_WHATSAPP_NUMBER:-}

      # Database
      - DATABASE_URL=postgresql+asyncpg://raccbuddy:raccbuddy@db:5432/raccbuddy

      # LLM Configuration
      - LLM_PROVIDER=\${LLM_PROVIDER:-ollama}
      - EMBEDDING_PROVIDER=\${EMBEDDING_PROVIDER:-ollama}

      # Ollama (use host.docker.internal to reach host machine's Ollama)
      - OLLAMA_BASE_URL=\${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
      - OLLAMA_MODEL=\${OLLAMA_MODEL:-llama3.2:3b}
      - OLLAMA_EMBED_MODEL=\${OLLAMA_EMBED_MODEL:-nomic-embed-text}

      # xAI (optional)
      - XAI_API_KEY=\${XAI_API_KEY:-}
      - XAI_MODEL=\${XAI_MODEL:-grok-4-1-fast-reasoning}

      # Optional settings
      - MAX_CONTEXT_TOKENS=\${MAX_CONTEXT_TOKENS:-4000}
      - NUDGE_CHECK_INTERVAL_MINUTES=\${NUDGE_CHECK_INTERVAL_MINUTES:-60}
      - OWNER_MEMORY_RETENTION_DAYS=\${OWNER_MEMORY_RETENTION_DAYS:-90}
    depends_on:
      - db
    restart: unless-stopped
    extra_hosts:
      - "host.docker.internal:host-gateway"

  whatsapp:
    image: ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG}
    environment:
      - PORT=3001
      - PYTHON_CORE_URL=http://app:8000
    volumes:
      - wa-session:/app/.wwebjs_auth
    depends_on:
      - db
      - app
    restart: unless-stopped

volumes:
  pgdata:
  wa-session:
EOF
echo -e "${GREEN}✓ Deployment docker-compose.yml created${NC}"
echo ""

# Step 11: Summary
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           🦝 Deployment Complete! 🦝                       ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Images pushed to Docker Hub:${NC}"
echo -e "  • ${DOCKER_USERNAME}/${APP_IMAGE}:${IMAGE_TAG}"
echo -e "  • ${DOCKER_USERNAME}/${WHATSAPP_IMAGE}:${IMAGE_TAG}"
echo ""
echo -e "${YELLOW}Backups created in:${NC} ${BACKUP_DIR}"
echo -e "  • database.sql.gz - PostgreSQL database dump"
echo -e "  • whatsapp-session.tar.gz - WhatsApp session data"
echo -e "  • docker-compose.yml - Ready-to-use compose file"
echo -e "  • deployment-info.txt - Deployment instructions"
echo ""
echo -e "${GREEN}Next steps for Umbrel deployment:${NC}"
echo -e "  1. Copy the backup directory to your Umbrel"
echo -e "  2. On Umbrel, create a .env file with your tokens"
echo -e "  3. Run: ${YELLOW}docker compose up -d${NC}"
echo -e "  4. Restore database: ${YELLOW}gunzip -c database.sql.gz | docker compose exec -T db psql -U raccbuddy raccbuddy${NC}"
echo -e "  5. Restore WhatsApp session if needed"
echo ""
echo -e "${GREEN}Happy deploying! 🚀${NC}"
