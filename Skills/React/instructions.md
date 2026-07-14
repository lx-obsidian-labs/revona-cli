# React Instructions

## Component Structure
- Prefer function components over class components
- Use TypeScript interfaces for props
- Default export for page components, named export for reusable components

```tsx
interface Props {
  title: string;
  children?: React.ReactNode;
}

export function Card({ title, children }: Props) {
  return (
    <div className="rounded-lg border p-4">
      <h2>{title}</h2>
      {children}
    </div>
  );
}
```

## State Management
- Use useState for local state
- Use useReducer for complex state
- Prefer React Query / SWR for server state
- Avoid prop drilling — compose components

## Styling
- Tailwind CSS utility classes
- Dark mode via `dark:` prefix
- Consistent spacing (4px base)

## Testing
- Vitest + @testing-library/react
- Test behavior, not implementation
