"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/Icon";

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const report = path.startsWith("/cases");
  return <div className="workspace">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="Committee home"><span className="brand-mark"><Icon name="layers" size={23} /></span><span>committee<span className="brand-sub">by Monobosses</span></span></Link>
      <div className="sidebar-label">YOUR WORKSPACE</div>
      <nav className="main-nav" aria-label="Workspace">
        <Link href="/" className={!report ? "active" : ""}><Icon name="plus" />New assessment</Link>
        <Link href="/cases/sample" className={report ? "active" : ""}><Icon name="book" />Example report<span className="nav-count">01</span></Link>
      </nav>
      <div className="sidebar-note"><span className="status-dot" /><strong>Frontend preview</strong><p>Explore the workflow with fictional evidence. Live analysis will be connected later.</p></div>
      <div className="sidebar-bottom"><span className="avatar">R</span><div><strong>Rinata</strong><span>Product & frontend</span></div><span className="team-pill">R1</span></div>
    </aside>
    <div className="workspace-body">
      <header className="topbar"><div className="breadcrumb">Workspace <span>/</span> <strong>{report ? "Underwriting report" : "New assessment"}</strong></div><span className="preview-pill"><span className="status-dot" />Synthetic preview</span></header>
      <main id="main-content" tabIndex={-1}>{children}</main>
      <footer className="workspace-footer"><span>Biology. Evidence. Better questions.</span><span>Local preview · No live analysis</span></footer>
    </div>
  </div>;
}
