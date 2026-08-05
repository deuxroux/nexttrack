import styles from "./Footer.module.css";

export function Footer() {
  return (
    <footer className={styles.footer}>
      <span className={styles.copy}>NextTrack is a stateless recommendation engine for playlist extension.</span>
      <nav className={styles.links} aria-label="Footer links">
        {/* wired in Iter 5 */}
        <a href="#privacy" className={styles.link}>Privacy</a>
        <a href="#guide" className={styles.link}>CSV → Soundiiz / TuneMyMusic guide</a>
      </nav>
    </footer>
  );
}
