import { IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";
import type { ParamsHandle } from "../hooks/useParams";
import type { SeedProfileHandle } from "../hooks/useSeedProfile";
import type { SeedsHandle } from "../hooks/useSeeds";
import styles from "./ParamsPanel.module.css";

interface Props {
  params: ParamsHandle;
  profile: SeedProfileHandle;
  seeds: SeedsHandle;
  onRecommend: () => void;
  streaming: boolean;
  progress: string | null;
  error: string | null;
}

interface SliderProps {
  id: string;
  label: string;
  min: number;
  max: number;
  value: number;
  onChange: (v: number) => void;
  fillPct: number;
  hint: string;
  tooltip: string;
}

function Slider({
  id,
  label,
  min,
  max,
  value,
  onChange,
  fillPct,
  hint,
  tooltip,
}: SliderProps) {
  const hintId = `${id}-hint`;
  return (
    <div className={styles.control}>
      <div className={styles.controlHeader}>
        <label htmlFor={id} className={styles.controlLabel}>
          {label}
          <span className={styles.tooltipWrap} title={tooltip}>
            <IconInfoCircle size={13} aria-label={tooltip} />
          </span>
        </label>
        <span className={styles.controlValue}>{value}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={e => onChange(+e.target.value)}
        className={styles.slider}
        style={{ "--fill": `${fillPct}%` } as React.CSSProperties}
        aria-describedby={hintId}
      />
      <p id={hintId} className={styles.hint}>
        {hint}
      </p>
    </div>
  );
}

export function ParamsPanel({
  params,
  profile,
  seeds,
  onRecommend,
  streaming,
  progress,
  error,
}: Props) {
  const [tagInput, setTagInput] = useState("");

  function handleTagInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (tagInput.trim()) {
        params.addGenreLock(tagInput.trim());
        setTagInput("");
      }
    }
  }

  const noveltyFill = params.novelty; //  0–100 default
  const diversityFill = ((params.artistDiversity - 1) / 9) * 100;
  const lengthFill = ((params.length - 5) / 45) * 100;

  return (
    <div className={styles.container}>

      <Slider
        id="novelty"
        label="Novelty"
        min={0}
        max={100}
        value={params.novelty}
        onChange={params.setNovelty}
        fillPct={noveltyFill}
        hint="Higher = favour obscure tracks; lower = familiar picks."
        tooltip="Controls how strongly popular tracks are penalised in ranking."
      />

      <Slider
        id="artist-diversity"
        label="Artist diversity"
        min={1}
        max={10}
        value={params.artistDiversity}
        onChange={params.setArtistDiversity}
        fillPct={diversityFill}
        hint="Max tracks from any one artist in results."
        tooltip="Limits the maximum number of recommended tracks per single artist."
      />

      <Slider
        id="length"
        label="Result length"
        min={5}
        max={50}
        value={params.length}
        onChange={params.setLength}
        fillPct={lengthFill}
        hint="Number of recommended tracks returned (5–50, default 10)."
        tooltip="How many tracks to include in the final recommendation."
      />

      {/*  Genre lock  */}
      <div className={styles.genreSection}>
        <p className={styles.sectionLabel}>Genre lock</p>

        {/* Active locks */}
        {params.genreLock.length > 0 && (
          <div className={styles.activeLocks} aria-label="Active genre locks">
            {params.genreLock.map(tag => (
              <span key={tag} className={styles.activeChip}>
                {tag}
                <button
                  className={styles.chipRemove}
                  onClick={() => params.removeGenreLock(tag)}
                  aria-label={`Remove genre ${tag}`}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Free-text tag input */}
        <input
          className={styles.tagInput}
          value={tagInput}
          onChange={e => setTagInput(e.target.value)}
          onKeyDown={handleTagInputKeyDown}
          placeholder="Type a genre and press Enter…"
          aria-label="Add genre tag"
        />

        {/* Suggest from seeds */}
        <button
          className={styles.suggestBtn}
          onClick={() => profile.fetchProfile(seeds.seeds)}
          disabled={!seeds.canRecommend || profile.loading}
          aria-label="Suggest genres from seeds"
        >
          {profile.loading ? "Loading…" : "Suggest genres from seeds"}
        </button>

        {/* Suggested chips are capped to top 10 */}
        {profile.tags.length > 0 && (
          <div className={styles.suggestedChips}>
            {profile.tags.map(t => {
              const active = params.genreLock.some(
                g => g.toLowerCase() === t.name.toLowerCase(),
              );
              return (
                <button
                  key={t.name}
                  className={styles.suggestChip}
                  data-active={active}
                  aria-pressed={active}
                  onClick={() => params.addGenreLock(t.name)}
                >
                  {t.name}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/*  Status / Recommend  */}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {streaming && progress && (
        <p className={styles.progress} role="status">
          {progress}
        </p>
      )}

      <button
        className={styles.recommendBtn}
        onClick={onRecommend}
        disabled={!seeds.canRecommend || streaming}
      >
        {streaming ? "Generating…" : "Recommend"}
      </button>
    </div>
  );
}
