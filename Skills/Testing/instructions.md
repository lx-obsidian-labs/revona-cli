# Testing Instructions

## Unit Tests (Vitest)
```ts
import { describe, it, expect } from 'vitest';
import { formatDate } from './date';

describe('formatDate', () => {
  it('formats ISO string to readable date', () => {
    expect(formatDate('2024-01-15')).toBe('Jan 15, 2024');
  });
});
```

## Component Tests (React Testing Library)
```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Card } from './Card';

describe('Card', () => {
  it('renders title and content', () => {
    render(<Card title="Hello"><p>World</p></Card>);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

## E2E Tests (Playwright)
```ts
import { test, expect } from '@playwright/test';

test('user can log in', async ({ page }) => {
  await page.goto('/login');
  await page.fill('[name=email]', 'user@example.com');
  await page.fill('[name=password]', 'password123');
  await page.click('button[type=submit]');
  await expect(page).toHaveURL('/dashboard');
});
```

## Configuration
Install: `npm install -D vitest @testing-library/react @playwright/test`
Vitest config in vitest.config.ts. Playwright config in playwright.config.ts.
