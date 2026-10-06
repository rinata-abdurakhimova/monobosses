import { Icon } from "@/components/Icon";
import type { Report } from "@/lib/types";

export function RecommendationCard({ report }: { report: Report }) {
  return <section className="recommendation-card" aria-labelledby="recommendation-heading"><div className="recommendation-top"><span className="eyebrow">COMMITTEE CONCLUSION</span><span className="recommendation-label"><span />{report.recommendation}</span></div><h2 id="recommendation-heading">A promising hypothesis.<br />Important conditions remain.</h2><p className="recommendation-rationale">{report.rationale}</p><div className="conditions"><span className="eyebrow">WHAT NEEDS TO BE TRUE</span><ol>{report.conditions.map((condition, i) => <li key={condition}><span>{String(i + 1).padStart(2, "0")}</span>{condition}</li>)}</ol></div><a className="recommendation-link" href="#section-human_translation_thesis">Inspect the decisive evidence<Icon name="arrow" size={17} /></a></section>;
}
