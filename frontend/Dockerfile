# --- Build stage: compile the React app -------------------------------------------------------
FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# Basemap style URLs are baked in at build time (Vite inlines import.meta.env). Empty = default.
ARG VITE_MAP_STYLE_URL=""
ARG VITE_MAP_STYLE_URL_DARK=""
ENV VITE_MAP_STYLE_URL=$VITE_MAP_STYLE_URL VITE_MAP_STYLE_URL_DARK=$VITE_MAP_STYLE_URL_DARK
RUN npm run build

# --- Runtime stage: static files + reverse proxy -----------------------------------------------
FROM nginx:1.30-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
