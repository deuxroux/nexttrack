import type { components } from "../api/schema";
import styles from "./Results.module.css";

type RecommendationResult = components["schemas"]["RecommendationResult"];

interface Props {
  result: RecommendationResult | null;
  onExport: () => void;
  exporting: boolean;
  exportError: string | null;
}

export function Results({ result, onExport, exporting, exportError }: Props) {
  const count = result?.candidates.length ?? 0;

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

      {/* Fallback D notice (2.11) — muted, not --danger */}
      {result?.pool_exhausted && (
        <p className={styles.exhausted}>
          Fewer tracks than requested — the candidate pool was exhausted.
        </p>
      )}

      {result ? (
        <ul className={styles.list}>
          {result.candidates.map((c) => (
            <li key={`${c.artist}|${c.title}`} className={styles.row}>
              <div className={styles.rowMeta}>
                <span className={styles.title}>{c.title}</span>
                <span className={styles.artist}>{c.artist}</span>
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
      ) : (
        <p className={styles.empty}>
          Add seeds and click Recommend to see results here.
        </p>
      )}
    </div>
  );
}
