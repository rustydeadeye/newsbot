export type ViewerRole = "admin" | "customer";

export type ViewerProfile = {
  workspace_user_id: number;
  user_id: string;
  email: string;
  role: ViewerRole;
  display_name: string | null;
};

export function getViewerLabel(role: ViewerRole): string {
  return role === "admin" ? "Admin" : "Customer";
}
