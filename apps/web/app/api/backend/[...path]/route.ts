import { proxyBackend } from "@/lib/api/backend-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handle(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  return proxyBackend(request, path, { baseUrl: process.env.API_BASE_URL });
}

export { handle as GET, handle as POST };
