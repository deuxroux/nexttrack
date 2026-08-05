import styles from "./App.module.css";
import { SeedBuilder } from "./components/SeedBuilder";
import { Footer } from "./components/Footer";
import { TopNav } from "./components/TopNav";
import { useSeeds } from "./hooks/useSeeds";

function App() {
  // lifted so Step 2 and Step 3 can read the same seed state in Iter 3
  const seeds = useSeeds();

  return (
    <div className={styles.layout}>
      <TopNav />
      <main className={styles.grid}>
        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 1</p>
          <h2 className={styles.panelTitle}>Seed playlist</h2>
          <SeedBuilder seeds={seeds} />
        </section>
        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 2</p>
          <h2 className={styles.panelTitle}>Tune</h2>
        </section>
        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 3</p>
          <h2 className={styles.panelTitle}>Results</h2>
        </section>
      </main>
      <Footer />
    </div>
  );
}

export default App;
