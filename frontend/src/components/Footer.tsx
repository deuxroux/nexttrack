import { useRef } from "react";
import styles from "./Footer.module.css";
import { GuideDialog, type GuideDialogHandle } from "./GuideDialog";
import { PrivacyDialog, type PrivacyDialogHandle } from "./PrivacyDialog";

export function Footer() {
  const privacyRef = useRef<PrivacyDialogHandle>(null);
  const guideRef = useRef<GuideDialogHandle>(null);

  return (
    <>
      <footer className={styles.footer}>
        <span className={styles.copy}>NextTrack is a stateless recommendation engine for playlist extension.</span>
        <nav className={styles.links} aria-label="Footer links">
          <button className={styles.dialogBtn} onClick={() => privacyRef.current?.open()}>
            Privacy
          </button>
          <button className={styles.dialogBtn} onClick={() => guideRef.current?.open()}>
            Importing to Streaming Service
          </button>
        </nav>
      </footer>
      <PrivacyDialog ref={privacyRef} />
      <GuideDialog ref={guideRef} />
    </>
  );
}
