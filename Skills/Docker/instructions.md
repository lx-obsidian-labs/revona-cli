# Docker Instructions

## Multi-stage Build Pattern
```dockerfile
# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Run
FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package*.json ./
EXPOSE 3000
CMD ["node", "dist/index.js"]
```

## Docker Compose for Dev
```yaml
version: '3.8'
services:
  app:
    build: .
    ports: ["3000:3000"]
    volumes: [".:/app"]
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/db
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: db
```

## Best Practices
- Use .dockerignore to exclude node_modules, .git, .env
- Pin versions (`node:20-alpine` not `node:latest`)
- Run as non-root user
- Scan images for vulnerabilities
