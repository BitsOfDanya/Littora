FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:24-slim AS build
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE_URL=/
ARG NEXT_PUBLIC_DEMO_FIXTURES=true
ARG LITTORA_API_PROXY_TARGET=http://backend:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_DEMO_FIXTURES=${NEXT_PUBLIC_DEMO_FIXTURES} \
    LITTORA_API_PROXY_TARGET=${LITTORA_API_PROXY_TARGET} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN groupadd --system --gid 10001 littora \
    && useradd --system --uid 10001 --gid littora littora
COPY --from=build --chown=littora:littora /app/public ./public
COPY --from=build --chown=littora:littora /app/.next/standalone ./
COPY --from=build --chown=littora:littora /app/.next/static ./.next/static
USER littora
EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=6 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/').then((r) => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
CMD ["node", "server.js"]
