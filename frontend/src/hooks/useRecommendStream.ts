import { fetchEventSource } from "@microsoft/fetch-event-source";
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "../api/client";
import { mapRecommendError, mapRecommendErrorCode } from "../api/errors";
import type { components } from "../api/schema";

type Track = components["schemas"]["Track"];
type RecommendationParams = components["schemas"]["RecommendationParams"];
type RecommendationResult = components["schemas"]["RecommendationResult"];

export interface RecommendStreamHandle {
  result: RecommendationResult | null;
  progress: string | null;
  error: string | null;
  streaming: boolean;
  run: (seeds: Track[], params: RecommendationParams) => void;
}

// stop streaming allows us to check if error vs reboot
class StopStream extends Error { }


export function useRecommendStream(): RecommendStreamHandle {
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  // controller for the current stream
  const abortRef = useRef<AbortController | null>(null);

  // stop stream
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  function run(seeds: Track[], params: RecommendationParams) {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setResult(null);
    setError(null);
    setProgress("Starting…");
    setStreaming(true);

    fetchEventSource(
      `${API_BASE}/recommend/stream`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seeds, params }),
        signal: ctrl.signal,
        openWhenHidden: true,

        onopen: async (response) => {
          if (response.ok) return;
          let errorCode: string | undefined;
          try {
            const body = (await response.json()) as { error?: string };
            errorCode = body.error;
          } catch {
            /* non-JSON body */
          }
          setError(mapRecommendError(response.status, errorCode));
          setStreaming(false);
          throw new StopStream();
        },

        //pass message for user affordance
        onmessage: (ev) => {
          switch (ev.event) {
            case "similarity": {
              const d = JSON.parse(ev.data) as {
                seeds_done: number;
                seeds_total: number;
              };
              setProgress(
                `Finding similar tracks… (${d.seeds_done}/${d.seeds_total})`,
              );
              break;
            }
            case "tags":
              setProgress("Matching tags…");
              // no "ranking" server event — transition client-side after tags
              setTimeout(() => setProgress("Ranking…"), 50);
              break;
            case "error": {
              const d = JSON.parse(ev.data) as { error?: string };
              setError(mapRecommendErrorCode(d.error));
              setProgress(null);
              setStreaming(false);
              ctrl.abort();   // stop before the trailing `done` event arrives
              break;
            }
            case "result": {
              const r = JSON.parse(ev.data) as RecommendationResult;
              setResult(r);
              setProgress(null);
              break;
            }
            case "done":
              ctrl.abort();
              break;
          }
        },

        onerror: (err) => {
          if (err instanceof DOMException && err.name === "AbortError")
            throw err;
          // error already handled in onopen
          if (err instanceof StopStream) throw err;
          // unexpected network error
          setError("Connection error. Please try again.");
          setStreaming(false);
          throw err; // don't retry
        },

        onclose: () => {
          setStreaming(false);
        },
      },
    ).catch(() => { /* terminal errors already surfaced in state */ });
  }

  return { result, progress, error, streaming, run };
}
