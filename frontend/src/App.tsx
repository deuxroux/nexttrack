import { useState } from "react";
import styles from "./App.module.css";
import type { components } from "./api/schema";
import { Footer } from "./components/Footer";
import { ParamsPanel } from "./components/ParamsPanel";
import { Results } from "./components/Results";
import { SeedBuilder } from "./components/SeedBuilder";
import { TopNav } from "./components/TopNav";
import { useCsvExport } from "./hooks/useCsvExport";
import { useParams } from "./hooks/useParams";
import { useRecommendStream } from "./hooks/useRecommendStream";
import { useSeedProfile } from "./hooks/useSeedProfile";
import { useSeeds } from "./hooks/useSeeds";

type RecommendationParams = components["schemas"]["RecommendationParams"];

function App() {
  // all three columns share the same seed and params state
  const seeds = useSeeds();
  const params = useParams();
  const profile = useSeedProfile();
  const stream = useRecommendStream();
  const csvExport = useCsvExport();
  // snapshot of params at the time Recommend was used so CSV uses for generation.
  const [lastRunParams, setLastRunParams] = useState<RecommendationParams | null>(null);

  function handleRecommend() {
    const snapshot = params.toParams();
    setLastRunParams(snapshot);
    stream.run(seeds.seeds, snapshot);
  }

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
          <ParamsPanel
            params={params}
            profile={profile}
            seeds={seeds}
            onRecommend={handleRecommend}
            streaming={stream.streaming}
            progress={stream.progress}
            error={stream.error}
          />
        </section>

        <section className={styles.panel}>
          <p className={styles.eyebrow}>Step 3</p>
          <h2 className={styles.panelTitle}>Results</h2>
          <Results
            result={stream.result}
            onExport={() => {
              if (lastRunParams) csvExport.export(seeds.seeds, lastRunParams);
            }}
            exporting={csvExport.exporting}
            exportError={csvExport.error}
          />
        </section>
      </main>
      <Footer />
    </div>
  );
}

export default App;
