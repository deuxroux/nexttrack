//ingest seeds for param tweaking step. call profile endpoint
import { useState } from "react";
import { api } from "../api/client";
import type { components } from "../api/schema";

type Track = components["schemas"]["Track"];
type TagCount = components["schemas"]["TagCount"];

const MAX_SUGGESTED_TAGS = 10;

export interface SeedProfileHandle {
  tags: TagCount[];
  loading: boolean;
  error: string | null;
  fetchProfile: (seeds: Track[]) => Promise<void>;
}

export function useSeedProfile(): SeedProfileHandle {
  const [tags, setTags] = useState<TagCount[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchProfile(seeds: Track[]) {
    if (seeds.length === 0) return;
    setLoading(true);
    setError(null);

    const { data, error: apiError } = await api.POST("/seed-profile", {
      body: { seeds },
    });

    setLoading(false);

    if (apiError || !data) {
      setError("Couldn't load genre suggestions.");
      return;
    }

    // trust server sort order (desc by seed_count); just cap the list
    setTags(data.tags.slice(0, MAX_SUGGESTED_TAGS));
  }

  return { tags, loading, error, fetchProfile };
}
