# Build from the repository root: shared contracts live outside apps/web.
FROM node:24-bookworm-slim AS build
WORKDIR /app/apps/web
ENV NEXT_TELEMETRY_DISABLED=1
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY contracts /app/contracts
COPY apps/web /app/apps/web
RUN npm run contracts:check && npm run build

FROM node:24-bookworm-slim AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
WORKDIR /app/apps/web
# Retain the installed dependencies, including the TypeScript config loader.
COPY --from=build --chown=node:node /app/apps/web /app/apps/web
COPY --from=build --chown=node:node /app/contracts /app/contracts
USER node
EXPOSE 3000
CMD ["sh", "-c", "exec node node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port ${PORT:-3000}"]
