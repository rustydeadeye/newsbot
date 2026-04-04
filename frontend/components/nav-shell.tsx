"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SignOutButton } from "@/components/sign-out-button";
import { getViewerLabel, ViewerProfile } from "@/lib/session";

type NavItem = {
  href: Route;
  label: string;
};

export function NavShell({
  viewer,
  items
}: {
  viewer: ViewerProfile;
  items: NavItem[];
}) {
  const pathname = usePathname();

  return (
    <>
      <div className="brand">
        <div className="brand-mark">N</div>
        <div>
          <h1>Newsbot</h1>
          <p>
            {viewer.role === "admin"
              ? "Monitor pipeline health, publishing readiness, and customer-facing output."
              : "Review what matters, refine the draft, and move content forward with confidence."}
          </p>
        </div>
      </div>
      <div className="role-switcher">
        <span className="role-label">Signed in as</span>
        <div className="stack">
          <div className="row space">
            <span>{viewer.display_name ?? viewer.email}</span>
            <span className="pill">{getViewerLabel(viewer.role)}</span>
          </div>
          <div className="card-subtle">{viewer.email}</div>
          <div className="inline-actions">
            <SignOutButton />
          </div>
        </div>
      </div>
      <nav className="nav">
        {items.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} className={active ? "nav-link active" : "nav-link"} href={item.href}>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
