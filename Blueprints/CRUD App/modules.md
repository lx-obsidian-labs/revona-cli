# CRUD App Modules

## Core Components
- **DataTable** — sortable, filterable, paginated table with row actions
- **ResourceForm** — auto-generated form from Zod schema
- **DeleteDialog** — confirmation dialog with optimistic deletion
- **EmptyState** — shown when no resources exist

## Server Actions
- `createResource(data)` — validates → inserts → revalidates
- `getResources(filters)` — queries with pagination
- `getResource(id)` — single record lookup
- `updateResource(id, data)` — validates → updates → revalidates
- `deleteResource(id)` — deletes → revalidates

## States to Handle
- **Loading** — skeleton tables and forms
- **Empty** — "No resources yet" with CTA
- **Error** — inline form errors, toast for action failures
- **Edge Cases** — duplicate slugs, long text, XSS in content
