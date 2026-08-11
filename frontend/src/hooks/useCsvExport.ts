import { useState } from "react";
import { API_BASE } from "../api/client";
import { mapRecommendError } from "../api/errors";
import type { components } from "../api/schema";

type Track = components["schemas"]["Track"];
type RecommendationParams = components["schemas"]["RecommendationParams"];

export interface CsvExportHandle {
  export: (seeds: Track[], params: RecommendationParams) => Promise<void>;
  exporting: boolean;
  error: string | null;
}

export function useCsvExport(): CsvExportHandle {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function exportCsv(seeds: Track[], params: RecommendationParams) {
    setExporting(true);
    setError(null);

    const res = await fetch(
      `${API_BASE}/recommend?format=csv`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seeds, params }),
      },
    );

    if (!res.ok) {
      let errorCode: string | undefined;
      try {
        const body = (await res.json()) as { error?: string };
        errorCode = body.error;
      } catch {
        /* non-JSON body */
      }
      setError(mapRecommendError(res.status, errorCode));
      setExporting(false);
      return;
    }

    const blob = await res.blob();
    // backend controls filename
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = disposition.match(/filename="([^"]+)"/);
    const filename = match ? match[1] : "nexttrack_export.csv";

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    setExporting(false);
  }

  return { export: exportCsv, exporting, error };
}
