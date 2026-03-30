import Link from "next/link";

import { PageHeader } from "@/components/page-header";

export function AccessDenied({
  title,
  description
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="page-grid">
      <PageHeader title={title} description={description} />
      <div className="panel empty-state">
        <div className="headline">Admin workspace required</div>
        <p className="card-subtle">
          This area is reserved for publishing operations and deeper system controls.
        </p>
        <div className="inline-actions">
          <Link className="button secondary" href="/">
            Return Home
          </Link>
        </div>
      </div>
    </div>
  );
}
