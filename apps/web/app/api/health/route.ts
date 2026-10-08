export const dynamic = "force-dynamic";

/** Website process health; pipeline readiness is checked separately. */
export function GET() {
  return Response.json(
    { status: "ok" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
