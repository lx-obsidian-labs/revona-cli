# API Service Modules

## Auth Module
- POST /auth/register — create account, return tokens
- POST /auth/login — validate credentials, return tokens
- POST /auth/refresh — refresh access token
- POST /auth/logout — invalidate refresh token
- Middleware: verify JWT, extract user context

## Users Module (Admin)
- GET /users — list users (paginated)
- GET /users/:id — get user
- PATCH /users/:id — update user
- DELETE /users/:id — delete user

## Error Handling
```ts
class AppError extends Error {
  constructor(
    public statusCode: number,
    public code: string,
    message: string,
    public details?: unknown
  ) { super(message); }
}

// Standard error response
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "..." } }
```

## Security
- Rate limiting (100 req/min per IP, 1000 req/min per authed user)
- JWT access tokens (15 min) + refresh tokens (7 days)
- CORS whitelist
- Helmet headers
- Input validation on all endpoints
