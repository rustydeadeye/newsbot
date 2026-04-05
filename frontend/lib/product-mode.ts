import type { Route } from "next";

import { ViewerRole } from "@/lib/session";

export const PRODUCT_MODE = process.env.NEXT_PUBLIC_PRODUCT_MODE ?? "default";
export const IS_AUTOPOST_MODE = PRODUCT_MODE === "autopost";

export const CUSTOMER_HOME_ROUTE = "/dashboard" as Route;
export const ADMIN_HOME_ROUTE = "/operations" as Route;

export function getRoleHomePath(role: ViewerRole): Route {
  return role === "admin" ? ADMIN_HOME_ROUTE : CUSTOMER_HOME_ROUTE;
}
