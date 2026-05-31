import { useState } from "react";
import type { ActivityEvent } from "./jobUi";

export function useActivityLog() {
  const [activityLog, setActivityLog] = useState<ActivityEvent[]>([
    { id: 1, time: Date.now(), level: "info", message: "Интерфейс загружен" }
  ]);

  function appendActivity(level: ActivityEvent["level"], message: string, detail?: string) {
    setActivityLog((current) => [
      { id: Date.now() + Math.random(), time: Date.now(), level, message, detail },
      ...current
    ].slice(0, 80));
  }

  return {
    activityLog,
    appendActivity
  };
}
