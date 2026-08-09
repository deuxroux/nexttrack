import { IconX } from "@tabler/icons-react";
import { forwardRef, type MouseEvent, useImperativeHandle, useRef } from "react";
import styles from "./PrivacyDialog.module.css";

export interface PrivacyDialogHandle {
  open: () => void;
}

export const PrivacyDialog = forwardRef<PrivacyDialogHandle>(function PrivacyDialog(_, ref) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useImperativeHandle(ref, () => ({
    open: () => dialogRef.current?.showModal(),
  }));

  // click on the dialog element itself is the same as a backdrop click
  function handleBackdropClick(e: MouseEvent<HTMLDialogElement>) {
    if (e.target === e.currentTarget) dialogRef.current?.close();
  }

  return (
    <dialog ref={dialogRef} className={styles.dialog} onClick={handleBackdropClick}>
      <div className={styles.panel}>
        <div className={styles.header}>
          <h2 className={styles.title}>Privacy</h2>
          <button
            className={styles.closeBtn}
            onClick={() => dialogRef.current?.close()}
            aria-label="Close privacy dialog"
          >
            <IconX size={18} />
          </button>
        </div>
        <div className={styles.body}>
          <p className={styles.placeholder}>NextTrack is stateless by design and no user data is stored, tracked, or persisted on the browser or on the host server. There are no cookies or webtrackers implemented so you can feel sure that your data is not being sold or any tracks are paid promotions. Every recommendation happens in the moment, and nothing about your session, your seeds, or your listening is tied back to you. All calls to external services are solely for track data and are handled the same way. Note that The one thing we do keep is a short-lived cache, which stores results by search query only  and clears itself every 14 days. If you'd like to carry your recommendations over to Spotify, Apple Music, or wherever you already listen, check out the export guide for a quick walkthrough. For full transparency, the entire NextTrack codebase is public and open to inspection at github.com/deuxroux/nexttrack. </p>
        </div>
      </div>
    </dialog>
  );
});
