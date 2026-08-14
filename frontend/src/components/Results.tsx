import type { components } from "../api/schema";
import styles from "./Results.module.css";

type RecommendationResult = components["schemas"]["RecommendationResult"];
type Candidate = components["schemas"]["Candidate"];

// average track similarity metric for human interpretable evalution
function perTrackSim(c: Candidate): number {
  return c.summed_similarity / Math.max(c.contributing_seeds.length, 1);
}

interface Props {
  result: RecommendationResult | null;
  onExport: () => void;
  exporting: boolean;
  exportError: string | null;
}

export function Results({ result, onExport, exporting, exportError }: Props) {
  const count = result?.candidates.length ?? 0;

  const avgSim = result
    ? Math.round(
      result.candidates.reduce((sum, c) => sum + perTrackSim(c), 0) /
      result.candidates.length * 100,
    )
    : null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        {result && (
          <span className={styles.count}>
            {count} track{count !== 1 ? "s" : ""}
          </span>
        )}
        <button
          className={styles.exportBtn}
          onClick={onExport}
          disabled={!result || exporting}
        >
          {exporting ? "Exporting…" : "Export CSV"}
        </button>
      </div>

      {exportError && (
        <p className={styles.exportError} role="alert">
          {exportError}
        </p>
      )}

      {/* Fallback notice*/}
      {result?.pool_exhausted && (
        <p className={styles.exhausted}>
          Fewer tracks than requested — the candidate pool was exhausted.
        </p>
      )}

      {result ? (
        <>
          <ul className={styles.list}>
            {result.candidates.map((c) => (
              <li key={`${c.artist}|${c.title}`} className={styles.row}>
                <div className={styles.rowMeta}>
                  <span className={styles.title}>{c.title}</span>
                  <span className={styles.artist}>{c.artist}</span>
                  <span className={styles.simBadge}>
                    {Math.round(perTrackSim(c) * 100)}% match
                  </span>
                </div>
                {c.matched_tags.length > 0 && (
                  <div className={styles.tags}>
                    {c.matched_tags.map((tag) => (
                      <span key={tag} className={styles.tagPill}>{tag}</span>
                    ))}
                  </div>
                )}
                {c.explanation.length > 0 && (
                  <p className={styles.explanation}>
                    {c.explanation.join(" · ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {avgSim !== null && (
            <p className={styles.avgSim}>Avg. similarity: {avgSim}%</p>
          )}
        </>
      ) : (
        <p className={styles.empty}>
          Add seeds and click Recommend to see results.
        </p>
      )}
    </div>
  );
}
