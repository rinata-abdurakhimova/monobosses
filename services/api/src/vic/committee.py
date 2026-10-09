"""Runtime bridge from pipeline role results to R5's rich Chair output."""
from vic.agents.business.chair import analyze_chair


async def synthesize_committee(results, audit, ctx, *, case, pack):
    upstream = {result.role_id.value: result for result in results}
    return await analyze_chair(case, pack, ctx, audit=audit, **upstream)
