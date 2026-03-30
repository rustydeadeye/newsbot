import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Newsbot Dashboard",
  description: "Operations dashboard for finance news automation"
};

const navItems = [
  { href: "/", label: "Review Queue" },
  { href: "/drafts", label: "Draft Review" },
  { href: "/events", label: "Events" },
  { href: "/jobs", label: "Publish Jobs" },
  { href: "/settings", label: "Settings" }
];

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="brand-mark">N</div>
              <div>
                <h1>Newsbot Desk</h1>
                <p>Review, approve, and ship finance updates without losing editorial control.</p>
              </div>
            </div>
            <nav className="nav">
              {navItems.map((item) => (
                <Link key={item.href} className="nav-link" href={item.href}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="content">{children}</main>
        </div>
      </body>
    </html>
  );
}
