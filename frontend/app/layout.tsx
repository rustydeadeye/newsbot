import type { Metadata } from "next";
import type { Route } from "next";

import { NavShell } from "@/components/nav-shell";
import { getRoleHomePath } from "@/lib/product-mode";
import { getServerViewer } from "@/lib/viewer";
import "./globals.css";

export const metadata: Metadata = {
  title: "Newsbot Dashboard",
  description: "Operations dashboard for finance news automation"
};

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
              <NavShell
                viewer={auth.viewer}
                items={[{ href: getRoleHomePath(auth.viewer.role) as Route, label: auth.viewer.role === "admin" ? "Wire Feed" : "Autopost" }]}
              />
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
