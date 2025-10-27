"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function MeetingPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/meeting/realtime");
  }, [router]);

  return null;
}


