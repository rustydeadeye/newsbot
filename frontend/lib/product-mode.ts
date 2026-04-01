import { ViewerRole } from "@/lib/session";

export const PRODUCT_MODE = process.env.NEXT_PUBLIC_PRODUCT_MODE ?? "default";
export const IS_AUTOPOST_MODE = PRODUCT_MODE === "autopost";

export function getRoleHomePath(role: ViewerRole): string {
  if (!IS_AUTOPOST_MODE) {
    return "/";
  }
  return role === "admin" ? "/wire" : "/autopost";
}
