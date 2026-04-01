import type { Metadata } from "next";
import type { Route } from "next";

import { NavShell } from "@/components/nav-shell";
import { getServerViewer } from "@/lib/viewer";
import "./globals.css";

export const metadata: Metadata = {
  title: "Newsbot Dashboard",
  description: "Operations dashboard for finance news automation"
};

const customerNavItems = [
  { href: "/" as Route, label: "Home" },
  { href: "/autopost" as Route, label: "Autopost" },
  { href: "/drafts" as Route, label: "Drafts" },
  { href: "/events" as Route, label: "Events" },
  { href: "/settings" as Route, label: "Settings" }
];

const adminNavItems = [
  { href: "/" as Route, label: "Home" },
  { href: "/drafts" as Route, label: "Drafts" },
  { href: "/events" as Route, label: "Events" },
  { href: "/jobs" as Route, label: "Publishing" },
  { href: "/wire" as Route, label: "Wire Feed" },
  { href: "/settings" as Route, label: "Settings" }
];

export default async function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  const auth = await getServerViewer();
  return (
    <html lang="en">
      <body>
        {auth ? (
          <div className="shell">
            <aside className="sidebar">
              <NavShell viewer={auth.viewer} items={auth.viewer.role === "admin" ? adminNavItems : customerNavItems} />
            </aside>
            <main className="content">{children}</main>
          </div>
        ) : (
          children
        )}
      </body>
    </html>
  );
}
