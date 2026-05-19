import { StudioListClient } from "./studio-list-client";

// Server component shell — list view lives in the client component
// because we hit the authenticated API from the browser token.

export default function StudioPage() {
  return <StudioListClient />;
}
