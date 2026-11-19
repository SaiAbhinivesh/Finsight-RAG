# FinSight web UI: two stages.
#   Stage 1 (node) builds the React app into static HTML/JS/CSS.
#   Stage 2 (nginx) serves those files: the final image has no Node and no source code.

# ---------- stage 1: build ----------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The browser calls the API directly, so this is the address as seen from the user's machine
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# ---------- stage 2: serve ----------
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
