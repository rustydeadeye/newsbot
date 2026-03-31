"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function ActiveRunRefresher({ active }: { active: boolean }) {
  const router = useRouter();

  useEffect(() => {
    if (!active) {
      return;
    }
    const intervalId = window.setInterval(() => {
      router.refresh();
    }, 4000);

    return () => window.clearInterval(intervalId);
  }, [active, router]);

  return null;
}
