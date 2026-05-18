/**
 * Auth token persistence — localStorage based.
 *
 * Trade-off: localStorage is vulnerable to XSS but simpler to wire than
 * httpOnly cookies for an MVP. We'll switch to cookies + CSRF when we
 * deploy to production.
 */

const TOKEN_KEY = "deevai.token";
const TENANT_SLUG_KEY = "deevai.tenant_slug";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string, tenantSlug?: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
  if (tenantSlug) {
    window.localStorage.setItem(TENANT_SLUG_KEY, tenantSlug);
  }
}

export function clearStoredToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(TENANT_SLUG_KEY);
}

export function getStoredTenantSlug(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TENANT_SLUG_KEY);
}

export function isLoggedIn(): boolean {
  return getStoredToken() !== null;
}
