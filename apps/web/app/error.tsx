"use client";

export default function ErrorPage({ reset }: { reset: () => void }) {
  return <div className="page-container"><section className="panel state-panel" role="alert"><span className="eyebrow">PREVIEW ERROR</span><h1>The interface could not open this view.</h1><p>Please try again. No live analysis is running.</p><button className="button button-primary" onClick={reset}>Try again</button></section></div>;
}
