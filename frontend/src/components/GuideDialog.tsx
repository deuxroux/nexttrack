import { IconX } from "@tabler/icons-react";
import { forwardRef, type MouseEvent, useImperativeHandle, useRef } from "react";
import styles from "./GuideDialog.module.css";

export interface GuideDialogHandle {
  open: () => void;
}

export const GuideDialog = forwardRef<GuideDialogHandle>(function GuideDialog(_, ref) {
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
          <h2 className={styles.title}>CSV to Streaming Service Guide</h2>
          <button
            className={styles.closeBtn}
            onClick={() => dialogRef.current?.close()}
            aria-label="Close guide dialog"
          >
            <IconX size={18} />
          </button>
        </div>
        <div className={styles.body}>
          <p className={styles.placeholder}>Every recommendation list you generate can be downloaded as a CSV file that can be opened in Excel, Google Sheets, etc. Each row is a track, and the columns give you everything you need to take your list elsewhere: the artist, the title, and two ready-made search links (one for Spotify, one for Apple Music) that jump straight to that track on either platform. Using these links, you can open each one, hit save, and seed a playlist by hand. It takes a little longer, but nothing leaves your control, and no outside service besides the one you prefer ever touches your list.
            <br />
            If you want your recommendations turned into a real playlist automatically, a tool like <a href="https://soundiiz.com/">Soundiiz</a> or <a href="https://www.tunemymusic.com/"> TuneMyMusic</a> can read the CSV and build the playlist for you in a few clicks. These services are useful, but they are run by other companies, entirely separate from NextTrack. I can't vouch for how they handle your data or protect your privacy, so use them at your own discretion and fully understand their terms before connecting any accounts.</p>
        </div>
      </div>
    </dialog>
  );
});
