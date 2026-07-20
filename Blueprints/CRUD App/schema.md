# CRUD App Schema

```prisma
model Resource {
  id        String   @id @default(cuid())
  title     String
  slug      String   @unique
  content   String?
  published Boolean  @default(false)
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
```

```ts
// Zod validation schema
import { z } from 'zod';

export const resourceSchema = z.object({
  title: z.string().min(1).max(200),
  slug: z.string().regex(/^[a-z0-9-]+$/),
  content: z.string().optional(),
  published: z.boolean().default(false),
});

export type ResourceInput = z.infer<typeof resourceSchema>;
```
