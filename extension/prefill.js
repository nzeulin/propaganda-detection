(() => {
  const url = new URL(location.href);
  const match = /^#veritascope-selection=([a-f0-9-]{36})$/.exec(url.hash);
  if (url.origin !== "http://153.92.222.180:8080" || !match) return;

  const id = match[1];
  const message = { type: "get-veritascope-selection", id };
  // Retain the extension token only as long as the initial handoff needs it.
  url.hash = "analysis";
  history.replaceState(history.state, "", url.href);
  prefill().catch(() =>
    showStatus(
      "Could not load the selection. Try opening it again from the source page.",
    ),
  );

  async function prefill() {
    const selection = await chrome.runtime.sendMessage(message);
    if (!selection?.text) {
      showStatus("Selection expired. Highlight the text and try again.");
      return;
    }

    const findInput = () => {
      const section = document.getElementById("analysis");
      const input = section?.querySelector(
        'textarea[aria-label="Article text to analyze"]',
      );
      if (!input) section?.querySelector("button.edit-input")?.click();
      return input;
    };
    const input = await waitForInput(findInput);
    if (!input) {
      showStatus("The VeritasScope text box could not be found.");
      return;
    }

    // Use the native setter so React's controlled input sees the input event.
    const setValue = Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    ).set;
    setValue.call(input, selection.text);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.scrollIntoView({ block: "center" });
    input.focus({ preventScroll: true });
    await chrome.runtime.sendMessage({ ...message, consumed: true });

    if (selection.truncated) {
      showStatus("The selection was shortened to 40,000 characters.");
    }
  }

  function waitForInput(findInput) {
    return new Promise((resolve) => {
      const check = () => {
        const input = findInput();
        if (input) finish(input);
      };

      const observer = new MutationObserver(check);
      const timeout = setTimeout(() => finish(null), 8_000);
      function finish(input) {
        observer.disconnect();
        clearTimeout(timeout);
        resolve(input);
      }
      observer.observe(document.body, { subtree: true, childList: true });
      check();
    });
  }

  function showStatus(text) {
    const status = document.createElement("p");
    status.setAttribute("role", "status");
    status.textContent = text;
    const inputPanel = document.querySelector("#analysis .input-column");
    (inputPanel ?? document.body).prepend(status);
    status.scrollIntoView({ block: "nearest" });
  }
})();
