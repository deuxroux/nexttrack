import { useState } from "react";
import type { components } from "../api/schema";

type Track = components["schemas"]["Track"];

export interface SeedsHandle {
  seeds: Track[];
  count: number;
  atCap: boolean;
  canRecommend: boolean;
  add: (track: Track) => void;
  remove: (index: number) => void;
}

const MAX_SEEDS = 50;

//format for ease of readability.
// TODO investigate if this holds when we have weird tracks like remixes or edits.
function normalize(t: Track) {
  return `${t.artist.toLowerCase().trim()}|${t.title.toLowerCase().trim()}`;
}

export function useSeeds(): SeedsHandle {
  const [seeds, setSeeds] = useState<Track[]>([]);

  function add(track: Track) {
    setSeeds(prev => {
      // block if at cap. reject duplicates
      if (prev.length >= MAX_SEEDS) return prev;
      const key = normalize(track);
      if (prev.some(s => normalize(s) === key)) return prev;
      return [...prev, track];
    });
  }

  function remove(index: number) {
    setSeeds(prev => prev.filter((_, i) => i !== index));
  }


  //full return object for use.
  return {
    seeds,
    count: seeds.length,
    atCap: seeds.length >= MAX_SEEDS,
    canRecommend: seeds.length >= 1,
    add,
    remove,
  };
}
