import type { Route } from "next";

import { ViewerRole } from "@/lib/session";

export const PRODUCT_MODE = process.env.NEXT_PUBLIC_PRODUCT_MODE ?? "default";
export const IS_AUTOPOST_MODE = PRODUCT_MODE === "autopost";

export function getRoleHomePath(role: ViewerRole): Route {
  if (!IS_AUTOPOST_MODE) {
    return "/" as Route;
  }
  return (role === "admin" ? "/wire" : "/autopost") as Route;
}
