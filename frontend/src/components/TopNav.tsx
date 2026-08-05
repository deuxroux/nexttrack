//code for the top naigation bar. uses
import { useHealth } from "../hooks/useHealth";
import styles from "./TopNav.module.css";

export function TopNav() {
  const { connected } = useHealth();

  return (
    <header className={styles.nav}>
      <div className={styles.brand}>
        <span className={styles.title}>NextTrack</span>
        <span className={styles.pill}>v0.1 · stateless</span>
      </div>
      <div className={styles.meta}>
        <span className={styles.privacy}>No cookies · no accounts</span>
        <span className={styles.badge} data-connected={connected}>
          <span className={styles.dot} aria-hidden="true" />
          {connected ? "Last.fm connected" : "Last.fm unavailable"}
        </span>
      </div>
    </header>
  );
}
