import { useState } from "react";
import type { components } from "../api/schema";

type RecommendationParams = components["schemas"]["RecommendationParams"];

//expose for recommendation
export interface ParamsHandle {
  novelty: number;
  artistDiversity: number;
  length: number;
  genreLock: string[];
  setNovelty: (v: number) => void;
  setArtistDiversity: (v: number) => void;
  setLength: (v: number) => void;
  addGenreLock: (tag: string) => void;
  removeGenreLock: (tag: string) => void;
  clearGenreLock: () => void;
  toParams: () => RecommendationParams;
}

const clamp = (v: number, min: number, max: number) =>
  Math.min(max, Math.max(min, Math.round(v)));

//hook to recommendation endpoint in api
export function useParams(): ParamsHandle {
  const [novelty, setNoveltyState] = useState(50);
  const [artistDiversity, setArtistDiversityState] = useState(3);
  const [length, setLengthState] = useState(10);
  const [genreLock, setGenreLock] = useState<string[]>([]);

  const setNovelty = (v: number) => setNoveltyState(clamp(v, 0, 100));
  const setArtistDiversity = (v: number) => setArtistDiversityState(clamp(v, 1, 10));
  const setLength = (v: number) => setLengthState(clamp(v, 5, 50));

  function addGenreLock(tag: string) {
    const trimmed = tag.trim();
    if (!trimmed) return;
    setGenreLock(prev => {
      // dedup case; preserve original
      if (prev.some(t => t.toLowerCase() === trimmed.toLowerCase())) return prev;
      return [...prev, trimmed];
    });
  }

  //delete lock
  function removeGenreLock(tag: string) {
    setGenreLock(prev =>
      prev.filter(t => t.toLowerCase() !== tag.toLowerCase()),
    );
  }

  //cast to object for recommendation body
  function toParams(): RecommendationParams {
    return {
      novelty: clamp(novelty, 0, 100),
      artist_diversity: clamp(artistDiversity, 1, 10),
      length: clamp(length, 5, 50),
      genre_lock: genreLock,
    };
  }

  return {
    novelty,
    artistDiversity,
    length,
    genreLock,
    setNovelty,
    setArtistDiversity,
    setLength,
    addGenreLock,
    removeGenreLock,
    clearGenreLock: () => setGenreLock([]),
    toParams,
  };
}
