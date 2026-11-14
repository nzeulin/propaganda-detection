import { useEffect, useRef, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";

type EvidenceSource = "visual" | "image_text" | "caption";
type ImageReport = {
  status: "signals_found" | "needs_context" | "no_clear_signals";
  description: string;
  image_text: string;
  text_status:
    "readable" | "partially_readable" | "unreadable" | "no_visible_text";
  caption_assessment: {
    stance:
      | "endorsed"
      | "rejected"
      | "neutrally_reported"
      | "unclear"
      | "not_provided";
    excerpt: string | null;
  };
  findings: {
    technique: string;
    explanation: string;
    evidence: { source: EvidenceSource; excerpt: string }[];
  }[];
  context_needed: string | null;
};

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const imageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const statusLabels = {
  signals_found: "Possible persuasion techniques",
  needs_context: "More context needed",
  no_clear_signals: "No clear persuasion techniques found",
};
const sourceLabels: Record<EvidenceSource, string> = {
  visual: "Visual detail",
  image_text: "Text in image",
  caption: "Post caption",
};
const stanceLabels = {
  endorsed: "Endorses the image’s message",
  rejected: "Challenges the image’s message",
  neutrally_reported: "Presents the image for reference",
  unclear: "Position unclear",
};

async function requestImageAnalysis(
  file: File,
  caption: string,
  signal: AbortSignal,
): Promise<ImageReport> {
  const body = new FormData();
  body.append("image", file);
  if (caption.trim()) body.append("caption", caption.trim());
  const response = await fetch("/api/v1/images/analyze", {
    method: "POST",
    body,
    signal,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 404 || response.status === 503) {
      throw new Error("Image analysis is unavailable on this server.");
    }
    if (typeof data?.detail === "string") throw new Error(data.detail);
    if (response.status === 413)
      throw new Error("Choose an image up to 5 MB and 16 megapixels.");
    throw new Error("Could not analyze the image. Try again.");
  }
  if (
    !data ||
    typeof data.description !== "string" ||
    !Object.hasOwn(statusLabels, data.status) ||
    !data.caption_assessment ||
    !Array.isArray(data.findings)
  ) {
    throw new Error("The server returned an unreadable image analysis.");
  }
  return data;
}

function ImageResults({ report }: { report: ImageReport }) {
  const { stance, excerpt } = report.caption_assessment;
  return (
    <section
      className="image-check-results"
      aria-labelledby="image-check-result-title"
    >
      <h3 id="image-check-result-title" role="status">
        {statusLabels[report.status]}
      </h3>
      <p>{report.description}</p>
      {report.findings.length > 0 && (
        <ul className="image-check-findings">
          {report.findings.map(
            ({ technique, explanation, evidence }, index) => (
              <li key={`${technique}-${index}`}>
                <h4>{technique.replaceAll("_", " ")}</h4>
                <p>{explanation}</p>
                <ul className="image-check-evidence">
                  {evidence.map(({ source, excerpt }, evidenceIndex) => (
                    <li key={evidenceIndex}>
                      <strong>{sourceLabels[source]}</strong>{" "}
                      {source === "visual" ? excerpt : <q>{excerpt}</q>}
                    </li>
                  ))}
                </ul>
              </li>
            ),
          )}
        </ul>
      )}
      {report.image_text && (
        <details className="image-check-transcript">
          <summary>
            {report.text_status === "partially_readable"
              ? "Text in image (partially readable)"
              : "Text in image"}
          </summary>
          <p>{report.image_text}</p>
        </details>
      )}
      {report.text_status === "unreadable" && (
        <p>Text in the image could not be read.</p>
      )}
      {stance !== "not_provided" && (
        <div className="image-check-caption-result">
          <h4>How the caption frames the image</h4>
          <p>{stanceLabels[stance]}</p>
          {excerpt && <blockquote>{excerpt}</blockquote>}
        </div>
      )}
      {report.context_needed && (
        <p className="image-check-context">{report.context_needed}</p>
      )}
    </section>
  );
}

export default function ImageAnalysis({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [caption, setCaption] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ImageReport | null>(null);

  useEffect(() => {
    const modal = dialog.current;
    if (modal && !modal.open) modal.showModal();
    return () => activeRequest.current?.abort();
  }, []);
  useEffect(() => {
    if (!file) {
      setPreview("");
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(next: File | undefined) {
    setReport(null);
    let message = "";
    if (next) {
      if (
        !imageTypes.has(next.type) &&
        !(
          (next.type === "" || next.type === "application/octet-stream") &&
          /\.(jpe?g|png|webp)$/i.test(next.name)
        )
      ) {
        message = "Choose a JPG, PNG or WebP image.";
      } else if (!next.size || next.size > MAX_IMAGE_BYTES) {
        message = next.size
          ? "Choose an image up to 5 MB."
          : "This file is empty.";
      }
    }
    setError(message);
    setFile(message ? null : (next ?? null));
    return !message;
  }

  function close() {
    activeRequest.current?.abort();
    activeRequest.current = null;
    onClose();
  }

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || activeRequest.current) return;
    const request = new AbortController();
    activeRequest.current = request;
    setReport(null);
    setError("");
    setPending(true);
    try {
      const result = await requestImageAnalysis(file, caption, request.signal);
      if (!request.signal.aborted) setReport(result);
    } catch (cause) {
      if (!request.signal.aborted) {
        setError(
          cause instanceof TypeError
            ? "Could not reach the server. Try again."
            : cause instanceof Error
              ? cause.message
              : "Could not analyze the image.",
        );
      }
    } finally {
      if (activeRequest.current === request) {
        activeRequest.current = null;
        setPending(false);
      }
    }
  }

  return createPortal(
    <dialog
      ref={dialog}
      className="image-check-dialog"
      aria-labelledby="image-check-title"
      onClose={close}
    >
      <div className="image-check-heading">
        <h2 id="image-check-title">Analyze an image</h2>
        <button
          type="button"
          className="image-check-close"
          aria-label="Close image analysis"
          onClick={() => dialog.current?.close()}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
      <form onSubmit={(event) => void analyze(event)}>
        <fieldset disabled={pending}>
          <label htmlFor="image-check-file">Image</label>
          <input
            id="image-check-file"
            type="file"
            autoFocus
            accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
            aria-describedby="image-check-file-help"
            onChange={(event) => {
              if (!selectFile(event.target.files?.[0])) event.target.value = "";
            }}
          />
          <p id="image-check-file-help" className="image-check-help">
            JPG, PNG or WebP up to 5 MB.
          </p>
          {preview && file && (
            <img
              className="image-check-preview"
              src={preview}
              alt="Selected image preview"
            />
          )}
          <label htmlFor="image-check-caption">
            Post caption <span>(optional)</span>
          </label>
          <textarea
            id="image-check-caption"
            rows={2}
            maxLength={2000}
            placeholder="Paste the caption that appeared with the image"
            value={caption}
            onChange={(event) => {
              setCaption(event.target.value);
              setReport(null);
              if (file) setError("");
            }}
          />
        </fieldset>
        <div className="image-check-actions">
          <button type="submit" disabled={!file || pending}>
            Analyze image
          </button>
          {pending && <p role="status">Analyzing image…</p>}
        </div>
        <p className="image-check-help">
          The image and any caption are sent to OpenAI.
        </p>
        {error && (
          <p className="image-check-error" role="alert">
            {error}
          </p>
        )}
      </form>
      {report && <ImageResults report={report} />}
    </dialog>,
    document.body,
  );
}
