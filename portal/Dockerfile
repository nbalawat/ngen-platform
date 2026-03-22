FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html

# SPA routing + API reverse proxy
RUN echo 'server { \
    listen 3000; \
    root /usr/share/nginx/html; \
    index index.html; \
    \
    location /api/tenant/ { proxy_pass http://tenant-service:8000/; proxy_set_header Host $host; } \
    location /api/registry/ { proxy_pass http://model-registry:8001/; proxy_set_header Host $host; } \
    location /api/gateway/ { proxy_pass http://model-gateway:8002/; proxy_set_header Host $host; } \
    location /api/workflow/ { proxy_pass http://workflow-engine:8003/; proxy_set_header Host $host; } \
    location /api/governance/ { proxy_pass http://governance-service:8004/; proxy_set_header Host $host; } \
    location /api/mcp/ { proxy_pass http://mcp-manager:8005/; proxy_set_header Host $host; } \
    location /api/onboard/ { proxy_pass http://onboarding-agent:8006/; proxy_set_header Host $host; } \
    location /api/metering/ { proxy_pass http://metering-service:8007/; proxy_set_header Host $host; } \
    \
    location / { \
        try_files $uri $uri/ /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
