//this module is for left hand column-- build seeds that will be fed to /recommend endpoint.
// this allows search and population of a playlist for extension

import { useId, useRef, useState } from "react";
import { useResolveSpotify } from "../hooks/useResolveSpotify";
import { useSearch } from "../hooks/useSearch";
import type { SeedsHandle } from "../hooks/useSeeds";
import styles from "./SeedBuilder.module.css";

interface Props {
  seeds: SeedsHandle;
}

export function SeedBuilder({ seeds }: Props) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const [spotifyUrl, setSpotifyUrl] = useState("");
  const spotify = useResolveSpotify();

  const { results, loading: searchLoading } = useSearch(query);
  const listboxId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  // dropdown visibility: open when results arrive and input is focused
  const showDropdown = dropdownOpen && results.length > 0;

  function handleQueryChange(e: React.ChangeEvent<HTMLInputElement>) {
    setQuery(e.target.value);
    setActiveIndex(-1);
    setDropdownOpen(true);
  }

  function selectResult(index: number) {
    const hit = results[index];
    if (!hit) return;
    seeds.add({ artist: hit.artist, title: hit.title });
    setQuery("");
    setActiveIndex(-1);
    setDropdownOpen(false);
  }

  //allow keyboard commands in last.fm search window
  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!showDropdown) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActiveIndex(i => Math.min(i + 1, results.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActiveIndex(i => Math.max(i - 1, 0));
        break;
      case "Enter":
        e.preventDefault();
        if (activeIndex >= 0) selectResult(activeIndex);
        break;
      case "Escape":
        setDropdownOpen(false);
        setActiveIndex(-1);
        break;
    }
  }

  function handleSearchBlur() {
    // delay so option click events can fire before the dropdown closes
    setTimeout(() => setDropdownOpen(false), 150);
  }

  async function handleSpotifyAdd() {
    if (!spotifyUrl.trim()) return;
    const track = await spotify.resolve(spotifyUrl.trim());
    if (track) {
      seeds.add(track);
      setSpotifyUrl("");
    }
  }

  const activeOptionId =
    showDropdown && activeIndex >= 0
      ? `${listboxId}-opt-${activeIndex}`
      : undefined;

  return (
    <div className={styles.container}>

      {/* ── Last.fm search (primary input) ── */}
      <div className={styles.searchSection}>
        <label htmlFor={`${listboxId}-input`} className={styles.label}>
          Search for a track
        </label>
        <div className={styles.searchWrap}>
          <input
            ref={inputRef}
            id={`${listboxId}-input`}
            className={styles.searchInput}
            role="combobox"
            aria-expanded={showDropdown}
            aria-haspopup="listbox"
            aria-controls={listboxId}
            aria-activedescendant={activeOptionId}
            aria-label="Search for a track"
            value={query}
            onChange={handleQueryChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setDropdownOpen(true)}
            onBlur={handleSearchBlur}
            placeholder="Artist or track name…"
            autoComplete="off"
          />
          {searchLoading && (
            <span className={styles.searchSpinner} aria-hidden="true">…</span>
          )}
          {showDropdown && (
            <ul
              id={listboxId}
              role="listbox"
              aria-label="Search results"
              className={styles.dropdown}
            >
              {results.map((hit, i) => (
                <li
                  key={`${hit.artist}|${hit.title}`}
                  id={`${listboxId}-opt-${i}`}
                  role="option"
                  aria-selected={i === activeIndex}
                  className={styles.option}
                  data-active={i === activeIndex}
                  onMouseDown={() => selectResult(i)}
                >
                  {hit.image && (
                    <img
                      src={hit.image}
                      alt=""
                      className={styles.thumb}
                      width={32}
                      height={32}
                    />
                  )}
                  <span className={styles.optionTitle}>{hit.title}</span>
                  <span className={styles.optionArtist}>{hit.artist}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── Spotify URL import (secondary / muted) ── */}
      <div className={styles.spotifySection}>
        <p className={styles.spotifyDivider}>or import via Spotify URL</p>
        <div className={styles.spotifyRow}>
          <input
            id={`${listboxId}-spotify`}
            className={styles.spotifyInput}
            value={spotifyUrl}
            onChange={e => setSpotifyUrl(e.target.value)}
            placeholder="https://open.spotify.com/track/…"
            aria-label="Spotify track URL"
          />
          <button
            className={styles.spotifyBtn}
            onClick={handleSpotifyAdd}
            disabled={spotify.loading || !spotifyUrl.trim()}
            aria-label="Add track from Spotify URL"
          >
            {spotify.loading ? "…" : "Add"}
          </button>
        </div>
        {spotify.notice && (
          <p className={styles.spotifyNotice} role="status">
            {spotify.notice}
          </p>
        )}
      </div>

      {/* ── Seed playlist (below both inputs) ── */}
      <div className={styles.seedSection}>
        <div className={styles.seedHeader}>
          <span className={styles.seedCount}>{seeds.count} / 50 tracks</span>
          {seeds.atCap && (
            <span className={styles.capNotice} role="status">
              Maximum 50 tracks reached.
            </span>
          )}
        </div>
        {seeds.seeds.length > 0 && (
          <ul className={styles.seedList} aria-label="Seed tracks">
            {seeds.seeds.map((seed, i) => (
              <li key={`${seed.artist}|${seed.title}|${i}`} className={styles.seedItem}>
                <span className={styles.seedTitle}>{seed.title}</span>
                <span className={styles.seedArtist}>{seed.artist}</span>
                <button
                  className={styles.removeBtn}
                  onClick={() => seeds.remove(i)}
                  aria-label={`Remove ${seed.title} by ${seed.artist}`}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

    </div>
  );
}
