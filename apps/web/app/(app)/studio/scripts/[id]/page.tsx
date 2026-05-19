import { StudioDetailClient } from "./studio-detail-client";

export default async function StudioScriptDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <StudioDetailClient scriptId={id} />;
}
