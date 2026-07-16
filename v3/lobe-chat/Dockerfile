ARG NODEJS_VERSION="24"

FROM node:${NODEJS_VERSION}-slim AS builder

ARG USE_CN_MIRROR

ENV DEBIAN_FRONTEND="noninteractive"

# Install build dependencies
RUN set -e && \
    if [ "${USE_CN_MIRROR:-false}" = "true" ]; then \
        sed -i "s/deb.debian.org/mirrors.ustc.edu.cn/g" "/etc/apt/sources.list.d/debian.sources"; \
    fi && \
    apt update && \
    apt install ca-certificates proxychains-ng -qy && \
    mkdir -p /distroless/bin /distroless/etc /distroless/etc/ssl/certs /distroless/lib && \
    cp /usr/lib/$(arch)-linux-gnu/libproxychains.so.4 /distroless/lib/libproxychains.so.4 && \
    cp /usr/lib/$(arch)-linux-gnu/libdl.so.2 /distroless/lib/libdl.so.2 && \
    cp /usr/bin/proxychains4 /distroless/bin/proxychains && \
    cp /etc/proxychains4.conf /distroless/etc/proxychains4.conf && \
    cp /usr/lib/$(arch)-linux-gnu/libstdc++.so.6 /distroless/lib/libstdc++.so.6 && \
    cp /usr/lib/$(arch)-linux-gnu/libgcc_s.so.1 /distroless/lib/libgcc_s.so.1 && \
    cp /usr/lib/$(arch)-linux-gnu/librt.so.1 /distroless/lib/librt.so.1 && \
    cp /usr/local/bin/node /distroless/bin/node && \
    cp /etc/ssl/certs/ca-certificates.crt /distroless/etc/ssl/certs/ca-certificates.crt && \
    rm -rf /tmp/* /var/lib/apt/lists/* /var/tmp/*

WORKDIR /app

# Copy source from fork
COPY lobe-chat/package.json lobe-chat/pnpm-workspace.yaml ./
COPY lobe-chat/.npmrc ./
COPY lobe-chat/packages ./packages
COPY lobe-chat/patches ./patches
COPY lobe-chat/apps/desktop/src/main/package.json ./apps/desktop/src/main/package.json

# Install dependencies
RUN set -e && \
    if [ "${USE_CN_MIRROR:-false}" = "true" ]; then \
        export SENTRYCLI_CDNURL="https://npmmirror.com/mirrors/sentry-cli"; \
        npm config set registry "https://registry.npmmirror.com/"; \
        echo 'canvas_binary_host_mirror=https://npmmirror.com/mirrors/canvas' >> .npmrc; \
    fi && \
    export COREPACK_NPM_REGISTRY=$(npm config get registry | sed 's/\/$//') && \
    npm i -g corepack@latest && \
    corepack enable && \
    corepack use $(sed -n 's/.*"packageManager": "\(.*\)".*/\1/p' package.json) && \
    pnpm i && \
    mkdir -p /deps && \
    cd /deps && \
    echo '{"name":"deps","private":true}' > package.json && \
    pnpm add pg drizzle-orm

# Copy full source
COPY lobe-chat/ .

# Build-time env vars (required by next build for static generation)
ENV KEY_VAULTS_SECRET="use-for-build" \
    AUTH_SECRET="use-for-build" \
    DATABASE_URL="postgres://postgres:password@localhost:5432/postgres" \
    DATABASE_DRIVER="node" \
    APP_URL="http://app.com"

# Reduce memory to avoid OOM, limit Turbopack parallelism
ENV NODE_OPTIONS="--max-old-space-size=2048" \
    TURBOPACK_WORKERS=1 \
    NEXT_TELEMETRY_DISABLED=1

# Remove pg_search migrations (not available in our PostgreSQL)
RUN rm -f /app/packages/database/migrations/0090_enable_pg_search.sql \
          /app/packages/database/migrations/0093_add_bm25_indexes_with_icu.sql && \
    node -e "var fs=require('fs');var j=JSON.parse(fs.readFileSync('/app/packages/database/migrations/meta/_journal.json','utf8'));j.entries=j.entries.filter(function(e){return ['0090_enable_pg_search','0093_add_bm25_indexes_with_icu'].indexOf(e.tag)<0});fs.writeFileSync('/app/packages/database/migrations/meta/_journal.json',JSON.stringify(j,null,2))"

# Prebuild and build
RUN pnpm exec tsx scripts/dockerPrebuild.mts
RUN rm -rf src/app/desktop "src/app/(backend)/trpc/desktop"
RUN pnpm run build:spa && pnpm run build:spa:mobile && pnpm run build:spa:auth && pnpm run build:spa:copy && DOCKER=true pnpm exec next build

## Runtime stage
FROM busybox:latest AS runtime

COPY --from=builder /distroless/ /

# Copy build output
COPY --from=builder /app/.next/standalone /app/
COPY --from=builder /app/.next/static /app/.next/static
COPY --from=builder /app/public/_spa /app/public/_spa
COPY --from=builder /app/packages/database/migrations /app/migrations
COPY --from=builder /app/scripts/migrateServerDB/docker.cjs /app/docker.cjs
COPY --from=builder /app/scripts/migrateServerDB/errorHint.js /app/errorHint.js

# Copy deps
COPY --from=builder /deps/node_modules/.pnpm /app/node_modules/.pnpm
COPY --from=builder /deps/node_modules/pg /app/node_modules/pg
COPY --from=builder /deps/node_modules/drizzle-orm /app/node_modules/drizzle-orm

# Copy server launcher
COPY --from=builder /app/scripts/serverLauncher/startServer.js /app/startServer.js
COPY --from=builder /app/scripts/_shared /app/scripts/_shared

# Copy custom icons/assets from our directory
COPY voproshalych_v2/v3/assets/icon-192x192.png /app/public/icons/icon-192x192.png
COPY voproshalych_v2/v3/assets/icon-192x192.maskable.png /app/public/icons/icon-192x192.maskable.png
COPY voproshalych_v2/v3/assets/icon-512x512.png /app/public/icons/icon-512x512.png
COPY voproshalych_v2/v3/assets/icon-512x512.maskable.png /app/public/icons/icon-512x512.maskable.png
COPY voproshalych_v2/v3/lobe-chat/custom.js /app/public/custom.js
COPY voproshalych_v2/v3/lobe-chat/consent.html /app/public/consent.html

RUN set -e && \
    addgroup -S -g 1001 nodejs && \
    adduser -D -G nodejs -H -S -h /app -u 1001 nextjs && \
    chown -R nextjs:nodejs /app /etc/proxychains4.conf

## Final image
FROM scratch

COPY --from=runtime / /

ENV NODE_ENV="production" \
    NODE_OPTIONS="--dns-result-order=ipv4first --use-openssl-ca" \
    HOSTNAME="0.0.0.0" \
    PORT="3210"

ENV APP_URL="" \
    API_KEY_SELECT_MODE="" \
    DEFAULT_AGENT_CONFIG="" \
    SYSTEM_AGENT="" \
    FEATURE_FLAGS="" \
    PROXY_URL=""

# Database
ENV KEY_VAULTS_SECRET="" \
    DATABASE_DRIVER="node" \
    DATABASE_URL=""

# Auth
ENV AUTH_SECRET="" \
    AUTH_SSO_PROVIDERS="" \
    AUTH_ALLOWED_EMAILS="" \
    AUTH_TRUSTED_ORIGINS="" \
    AUTH_DISABLE_EMAIL_PASSWORD="" \
    AUTH_EMAIL_VERIFICATION="" \
    AUTH_ENABLE_MAGIC_LINK="" \
    AUTH_GOOGLE_ID="" \
    AUTH_GOOGLE_SECRET="" \
    AUTH_GITHUB_ID="" \
    AUTH_GITHUB_SECRET="" \
    AUTH_MICROSOFT_ID="" \
    AUTH_MICROSOFT_SECRET="" \
    AUTH_MICROSOFT_AUTHORITY_URL="" \
    AUTH_MICROSOFT_TENANT_ID=""

# Redis
ENV REDIS_URL="" \
    REDIS_PREFIX="" \
    REDIS_TLS=""

# Email
ENV EMAIL_SERVICE_PROVIDER="" \
    SMTP_HOST="" \
    SMTP_PORT="" \
    SMTP_SECURE="" \
    SMTP_USER="" \
    SMTP_PASS="" \
    SMTP_FROM="" \
    RESEND_API_KEY="" \
    RESEND_FROM=""

# S3 — not set to empty strings to avoid env validation errors

USER 1001

EXPOSE 3210/tcp

ENTRYPOINT ["/bin/node"]
CMD ["/app/startServer.js"]
