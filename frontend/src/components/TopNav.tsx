//code for the top naigation bar. uses
import logoUrl from "../assets/nexttrack_mark_bare.svg";
import { useHealth } from "../hooks/useHealth";
import styles from "./TopNav.module.css";

export function TopNav() {
  const { connected } = useHealth();

  return (
    <header className={styles.nav}>
      <div className={styles.brand}>
        <img src={logoUrl} alt="NextTrack logo" className={styles.logo} aria-hidden="true" />
        <span className={styles.title}>NextTrack</span>
        <span className={styles.pill}>Stateless Music Recommender</span>
      </div>
      <div className={styles.meta}>
        <span className={styles.badge} data-connected={connected}>
          <span className={styles.dot} aria-hidden="true" />
          {connected ? "Services connected" : "Services unavailable"}
        </span>
      </div>
    </header>
  );
}
