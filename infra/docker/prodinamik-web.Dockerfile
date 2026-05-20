# ──────────────────────────────────────────────────
# Prodinamik Engine — Web Dockerfile
# React SPA (Vite) + Nginx multi-stage build
# ──────────────────────────────────────────────────
# Build:  docker build -t prodinamik-web -f infra/docker/prodinamik-web.Dockerfile .
# Run:    docker run -d -p 80:80 prodinamik-web
# ──────────────────────────────────────────────────

# ── Stage 1: Build ──
FROM node:20-alpine AS build

LABEL stage="build"

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /build

# ── Copy workspace config ──
# (package.json + pnpm-workspace.yaml define the monorepo structure)
COPY web/package.json web/pnpm-workspace.yaml ./

# ── Copy lib packages (workspace deps) ──
COPY web/lib/api-client-react/ ./lib/api-client-react/
COPY web/lib/api-zod/ ./lib/api-zod/
COPY web/lib/db/ ./lib/db/

# ── Copy the UI app source ──
COPY web/artifacts/prodinamik-ui/ ./artifacts/prodinamik-ui/
COPY web/tsconfig.base.json ./tsconfig.base.json

# ── Install dependencies ──
# No frozen lockfile — first build generates it
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --no-frozen-lockfile

# ── Build the web app ──
# PORT and BASE_PATH are required by the Vite config
RUN cd artifacts/prodinamik-ui && \
    PORT=3000 BASE_PATH=/ pnpm build

# Verify the build output exists
RUN test -d artifacts/prodinamik-ui/dist/public && \
    echo "✅ Build successful: $(ls artifacts/prodinamik-ui/dist/public/ | wc -l) assets"

# ── Stage 2: Production (Nginx) ──
FROM nginx:alpine AS production

LABEL org.opencontainers.image.title="Prodinamik Engine Web UI"
LABEL org.opencontainers.image.description="Pipeline Engine Control Plane — React SPA"
LABEL org.opencontainers.image.version="1.3.0"
LABEL org.opencontainers.image.licenses="MIT"
LABEL maintainer="Yunus Güngör <mail@yunusgungor.com>"

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config (reverse proxy to API)
COPY infra/nginx/prodinamik-web.conf /etc/nginx/conf.d/prodinamik-web.conf

# Copy built SPA assets
COPY --from=build /build/artifacts/prodinamik-ui/dist/public/ /usr/share/nginx/html/

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
