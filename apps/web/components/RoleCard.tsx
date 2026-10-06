import type { RoleResult } from "@/lib/types";

export function RoleCard({ role }: { role: RoleResult }) {
  return (
    <article className="role-card">
      <div className="role-heading">
        <span className="role-initials">{role.initials}</span>
        <h3>{role.name}</h3>
      </div>
      <span className="role-position">{role.position}</span>
      <p>{role.summary}</p>
      <div className="role-unknown">
        <span>Key unknown</span>
        <strong>{role.unknown}</strong>
      </div>
    </article>
  );
}
