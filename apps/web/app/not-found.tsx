import Link from "next/link";

export default function NotFound() {
  return (
    <div className="page-container">
      <section className="panel state-panel">
        <span className="eyebrow">PAGE NOT FOUND</span>
        <h1>Let’s start with a new question.</h1>
        <p>This page is not part of the preview workspace.</p>
        <Link
          href="/"
          className="button button-primary"
        >
          New assessment
        </Link>
      </section>
    </div>
  );
}
