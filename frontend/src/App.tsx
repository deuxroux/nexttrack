import styles from "./App.module.css";
import { Footer } from "./components/Footer";
import { TopNav } from "./components/TopNav";

function App() {
  return (
    <div className={styles.layout}>
      <TopNav />
      <main className={styles.grid}>
        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 1</p>
          <h2 className={styles.panelTitle}></h2>
        </section>
        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 2</p>
          <h2 className={styles.panelTitle}></h2>
        </section>
        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 3</p>
          <h2 className={styles.panelTitle}></h2>
        </section>
      </main>
      <Footer />
    </div>
  );
}

export default App;
