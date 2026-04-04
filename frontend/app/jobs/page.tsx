import { redirect } from "next/navigation";

import { getRoleHomePath } from "@/lib/product-mode";
import { requireServerViewer } from "@/lib/viewer";

export default async function JobsPage() {
  const { viewer } = await requireServerViewer();
  redirect(getRoleHomePath(viewer.role));
}
