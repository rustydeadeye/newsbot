export type ViewerRole = "admin" | "customer";

export type ViewerProfile = {
  user_id: string;
  email: string;
  role: ViewerRole;
  display_name: string | null;
};

export function getViewerLabel(role: ViewerRole): string {
  return role === "admin" ? "Admin" : "Customer";
}
