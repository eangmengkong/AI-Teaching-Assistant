'use client';

import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import AppShell from '../../components/AppShell';
import { isLoggedIn } from '../../lib/auth';

/**
 * Route-group layout for the dashboard: requires a stored token before
 * rendering the responsive shell. The /login page lives outside this group
 * so it renders fully without the auth gate or sidebar.
 */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <div className="grid min-h-screen place-items-center bg-app-bg text-sm text-app-muted">
        Loading dashboard…
      </div>
    );
  }

  if (!isLoggedIn()) {
    // Client-side redirect: no valid token stored yet.
    window.location.replace('/login');
    return null;
  }

  return <AppShell>{children}</AppShell>;
}