# API Service Architecture

## Layers
1. **Routes** — define endpoints, attach middleware, delegate to handlers
2. **Middleware** — auth, rate-limit, validation, error handler
3. **Handlers** — request parsing, business logic delegation
4. **Services** — business logic, external API calls
5. **Repository** — database access layer
6. **Schema** — Zod/DTO definitions

## Request Lifecycle
```
Request → Rate Limiter → Auth → Validation → Handler → Service → Repository → Response
                                                          ↓
                                                    Error Handler → Error Response
```

## Structure
```
src/
  routes/
    auth.routes.ts
    users.routes.ts
  middleware/
    auth.ts
    rate-limit.ts
    validate.ts
    error-handler.ts
  handlers/
    auth.handler.ts
  services/
    auth.service.ts
    email.service.ts
  repositories/
    user.repository.ts
  schemas/
    auth.schema.ts
    user.schema.ts
  app.ts
  server.ts
```
