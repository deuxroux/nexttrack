import { useState } from "react";
import { api } from "../api/client";
import type { components } from "../api/schema";

type Track = components["schemas"]["Track"];

const FALLBACK_MSG =
  "Couldn't resolve that Spotify URL. Please use search to add the track manually.";

export function useResolveSpotify(): {
  resolve: (url: string) => Promise<Track | null>;
  notice: string | null;
  loading: boolean;
  clearNotice: () => void;
} {
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function resolve(url: string): Promise<Track | null> {
    setLoading(true);
    setNotice(null);

    const { data, error } = await api.POST("/resolve-spotify-url", {
      body: { url },
    });

    setLoading(false);

    if (error || !data) {
      // any non standard http code like 400 all surface the same fallback
      //notice will be non-blocking
      setNotice(FALLBACK_MSG);
      return null;
    }

    return data as Track;
  }

  return { resolve, notice, loading, clearNotice: () => setNotice(null) };
}
