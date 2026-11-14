import { useRef, useState, type ComponentType } from "react";
import "./ImageAnalysis.css";

export function ImageAnalysisButton() {
  const trigger = useRef<HTMLButtonElement>(null);
  const [Dialog, setDialog] = useState<ComponentType<{
    onClose: () => void;
  }> | null>(null);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState(false);

  async function open() {
    setOpening(true);
    setError(false);
    try {
      const { default: ImageAnalysis } = await import("./ImageAnalysis");
      setDialog(() => ImageAnalysis);
    } catch {
      setError(true);
    } finally {
      setOpening(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="image-check-trigger"
        aria-haspopup="dialog"
        ref={trigger}
        disabled={opening}
        onClick={() => void open()}
      >
        {opening ? "Opening…" : "Add image"}
      </button>
      {error && (
        <p className="image-check-error" role="alert">
          Could not open image analysis. Reload the page and try again.
        </p>
      )}
      {Dialog && (
        <Dialog
          onClose={() => {
            setDialog(null);
            trigger.current?.focus();
          }}
        />
      )}
    </>
  );
}
