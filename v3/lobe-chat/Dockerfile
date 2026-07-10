FROM lobehub/lobe-chat:latest AS base

FROM alpine:latest AS patcher

WORKDIR /app

COPY --from=base /app /app

# Replace brand text in JS bundles
RUN find /app/.next -name "*.js" -exec sed -i 's/LobeHub/Вопрошалыч/g' {} + && \
    find /app/.next -name "*.js" -exec sed -i "s/LobeHub Cloud/Вопрошалыч/g" {} + && \
    find /app/.next -name "*.js" -exec sed -i 's/LobeHub/Вопрошалыч/g' /app/server.js 2>/dev/null \; || true

# Replace brand in manifest and other files
RUN find /app -name "*.json" -exec sed -i 's/LobeHub/Вопрошалыч/g' {} + 2>/dev/null || true

FROM scratch

COPY --from=base / /

COPY --from=patcher /app/.next /app/.next
COPY --from=patcher /app/server.js /app/server.js
COPY --from=patcher /app/public /app/public

COPY assets/icon-192x192.png /app/public/icons/icon-192x192.png
COPY assets/icon-192x192.maskable.png /app/public/icons/icon-192x192.maskable.png
COPY assets/icon-512x512.png /app/public/icons/icon-512x512.png
COPY assets/icon-512x512.maskable.png /app/public/icons/icon-512x512.maskable.png

ENV NODE_ENV="production" \
    NODE_OPTIONS="--dns-result-order=ipv4first --use-openssl-ca" \
    HOSTNAME="0.0.0.0" \
    PORT="3210"

USER 1001

EXPOSE 3210/tcp

ENTRYPOINT ["/bin/node"]
CMD ["/app/startServer.js"]
