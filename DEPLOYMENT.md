# Deployment Scripts

This directory contains scripts for deploying RaccBuddy to Docker Hub and restoring backups on production servers (like Umbrel).

## Files

- **deploy-to-dockerhub.sh** - Builds multi-platform images, pushes to Docker Hub, and creates backups
- **restore-from-backup.sh** - Restores database and WhatsApp session from backups

## Quick Start

### 1. Deploy from Development Machine

```bash
# Set your Docker Hub username
export DOCKER_USERNAME=yourusername

# Optional: specify a tag (default is 'latest')
export IMAGE_TAG=v1.0.0

# Run deployment script
./deploy-to-dockerhub.sh
```

**What this does:**
- Logs into Docker Hub (you'll be prompted)
- Creates multi-platform builder (if needed)
- Builds images for `linux/amd64` and `linux/arm64`
- Pushes images to Docker Hub
- Dumps PostgreSQL database to `./backups/YYYYMMDD_HHMMSS/database.sql.gz`
- Backs up WhatsApp session to `./backups/YYYYMMDD_HHMMSS/whatsapp-session.tar.gz`
- Creates deployment-ready `docker-compose.yml` in backup directory
- Generates deployment instructions

### 2. Deploy on Production Server (Umbrel, etc.)

#### Option A: Using the restore script (Recommended)

```bash
# Transfer backup directory to server
scp -r backups/20260223_120000/ user@server:~/raccbuddy/

# SSH into server
ssh user@server

# Navigate to backup directory
cd ~/raccbuddy/backups/20260223_120000/

# Create .env file with your credentials
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=your-bot-token-here
OWNER_TELEGRAM_ID=123456789
OWNER_WHATSAPP_NUMBER=+1234567890
EOF

# Start containers
docker compose up -d

# Wait for database to be ready
sleep 30

# Run restore script (assuming script is in root)
bash ../../restore-from-backup.sh .
```

#### Option B: Manual restoration

```bash
# Start containers
docker compose up -d

# Restore database
gunzip -c database.sql.gz | docker compose exec -T db psql -U raccbuddy raccbuddy

# Restore WhatsApp session (to avoid re-scanning QR)
docker run --rm \
  -v raccbuddy_wa-session:/data \
  -v $(pwd):/backup \
  alpine sh -c "cd /data && tar xzf /backup/whatsapp-session.tar.gz"

# Restart services
docker compose restart
```

## Environment Variables

### Required
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from @BotFather
- `OWNER_TELEGRAM_ID` - Your Telegram user ID (get from bot with /start)

### Optional but Recommended
- `OWNER_WHATSAPP_NUMBER` - Your WhatsApp number (format: +1234567890)
- `LLM_PROVIDER` - `ollama` (default, local) or `xai` (cloud, better function calling)
- `OLLAMA_BASE_URL` - URL to Ollama server (default: http://host.docker.internal:11434)
- `XAI_API_KEY` - xAI API key if using xAI provider
- `MAX_CONTEXT_TOKENS` - Max tokens for LLM context (default: 4000)
- `NUDGE_CHECK_INTERVAL_MINUTES` - How often to check for nudges (default: 60)
- `OWNER_MEMORY_RETENTION_DAYS` - Days to keep old messages (default: 90)

## Updating Deployed Images

To deploy updates:

```bash
# On dev machine: rebuild and push
./deploy-to-dockerhub.sh

# On production: pull and restart
docker compose pull
docker compose up -d
```

## Backup Structure

Each backup creates a timestamped directory:

```
backups/
└── 20260223_120000/
    ├── database.sql          # Raw SQL dump
    ├── database.sql.gz       # Compressed SQL dump
    ├── whatsapp-session.tar.gz  # WhatsApp auth session
    ├── docker-compose.yml    # Ready-to-use compose file
    └── deployment-info.txt   # Instructions and image info
```

## Troubleshooting

### Docker buildx not available
```bash
# Install buildx (usually comes with Docker 19.03+)
docker buildx create --use
```

### Build fails on Apple Silicon
```bash
# Make sure Rosetta is enabled in Docker Desktop
# Docker Desktop > Settings > General > "Use Rosetta for x86_64/amd64..."
```

### Database restore fails
```bash
# Make sure containers are running
docker compose ps

# Check database logs
docker compose logs db

# Ensure PostgreSQL is ready
docker compose exec db pg_isready -U raccbuddy
```

### WhatsApp session restore doesn't work
```bash
# Check volume exists
docker volume ls | grep wa-session

# If needed, just re-scan QR code instead
# WhatsApp will work without session backup, you'll just need to scan again
docker compose logs whatsapp
```

## Platform Support

The multi-platform build supports:
- **linux/amd64** - Intel/AMD x86_64 (most servers, Umbrel)
- **linux/arm64** - ARM 64-bit (Raspberry Pi 4+, some home servers)

Built from Apple Silicon (M1/M2/M3), but runs on any platform above.

## Security Notes

- Never commit `.env` files with real credentials
- Use environment variables or Docker secrets in production
- The backup scripts preserve your WhatsApp session - keep backups secure
- Database dumps contain all your messages - encrypt if storing off-site

## Need Help?

- Check the main [README.md](README.md) for general setup
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines
- Open an issue on GitHub if you encounter problems
