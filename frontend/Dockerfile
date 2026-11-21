# syntax=docker/dockerfile:1

# ---- Stage 1: install dependencies, test and build the static bundle ----------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm test && npm run build

# ---- Stage 2: tiny static file server (non-root nginx) ------------------------------------
FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime
ENV API_BASE_URL=http://localhost:8000
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 docker/40-app-config.sh /docker-entrypoint.d/40-app-config.sh
COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
