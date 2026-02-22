FROM node:20-slim

# whatsapp-web.js needs chromium
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Tell puppeteer to use system chromium
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --production

COPY . .

# Session data persisted via volume
VOLUME ["/app/.wwebjs_auth"]

EXPOSE 3001

CMD ["node", "src/index.js"]
