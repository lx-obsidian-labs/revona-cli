# CRUD App Architecture

## Layers
1. **Routes** — `app/resources/[id]/` pages (list, create, edit, show, delete)
2. **Server Actions** — `app/resources/actions.ts` (createResource, updateResource, deleteResource)
3. **Database** — Prisma schema with Resource model
4. **Validation** — Zod schemas shared between client and server
5. **UI** — Reusable DataTable, Form, Modal components

## Data Flow
```
User Action → Server Action → Prisma → Database
                  ↓
            Revalidate Path
                  ↓
          Re-render Page
```

## File Structure
```
app/resources/
  page.tsx          — list (table)
  new/page.tsx      — create form
  [id]/page.tsx     — show detail
  [id]/edit/page.tsx — edit form
  actions.ts        — server actions
components/
  DataTable.tsx
  ResourceForm.tsx
  DeleteDialog.tsx
lib/
  db.ts             — Prisma client
  schemas.ts        — Zod schemas
```
