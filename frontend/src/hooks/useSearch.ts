import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { components } from "../api/schema";

type TrackHit = components["schemas"]["TrackHit"];

export function useSearch(query: string): {
  results: TrackHit[];
  loading: boolean;
  error: string | null;
} {
  const [results, setResults] = useState<TrackHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    let ignore = false;
    setLoading(true);
    setError(null);

    //set timeout for debounce of results
    const timer = setTimeout(() => {
      api
        .GET("/search", { params: { query: { q: query.trim(), limit: 8 } } })
        .then(({ data }) => {
          if (!ignore) {
            setResults(data ?? []);
            setLoading(false);
          }
        })
        .catch(() => {
          if (!ignore) {
            setError("Search unavailable.");
            setLoading(false);
          }
        });
    }, 250);

    return () => {
      // cancel if in debounce
      ignore = true;
      clearTimeout(timer);
    };
  }, [query]);

  return { results, loading, error };
}
