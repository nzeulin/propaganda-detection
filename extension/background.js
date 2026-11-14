const VERITASCOPE_URL = "http://153.92.222.180:8080/";
const VERITASCOPE_ORIGIN = new URL(VERITASCOPE_URL).origin;
const MENU_ID = "open-in-veritascope";
const MAX_SELECTION_LENGTH = 40_000;
const MAX_PENDING = 10;
const SELECTION_TTL_MS = 5 * 60_000;

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Open in VeritasScope",
    contexts: ["selection"],
    documentUrlPatterns: ["http://*/*", "https://*/*"],
  });
});

chrome.contextMenus.onClicked.addListener((info) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText?.trim()) return;
  openSelection(info.selectionText).catch((error) => {
    console.error("Could not open VeritasScope", error);
  });
});

// Serialize storage updates so that two quick clicks keep separate selections.
let pendingOpen = Promise.resolve();

function openSelection(text) {
  const action = pendingOpen.then(async () => {
    const id = crypto.randomUUID();
    const createdAt = Date.now();
    const points = Array.from(text);
    const selection = {
      text:
        points.length <= MAX_SELECTION_LENGTH
          ? text
          : points.slice(0, MAX_SELECTION_LENGTH).join(""),
      truncated: points.length > MAX_SELECTION_LENGTH,
      createdAt,
    };
    const prefix = "selection:";
    const key = prefix + id;
    const storage = chrome.storage.session;
    const saved = Object.entries(await storage.get(null))
      .filter(([name]) => name.startsWith(prefix))
      .sort(([, a], [, b]) => b.createdAt - a.createdAt);
    const toRemove = saved
      .filter(
        ([, value], index) =>
          index >= MAX_PENDING - 1 ||
          createdAt - value.createdAt > SELECTION_TTL_MS,
      )
      .map(([name]) => name);

    if (toRemove.length) await storage.remove(toRemove);
    await storage.set({ [key]: selection });
    const url = new URL(VERITASCOPE_URL);
    url.hash = `veritascope-selection=${id}`;
    try {
      await chrome.tabs.create({ url: url.href });
    } catch (error) {
      await storage.remove(key);
      throw error;
    }
  });
  pendingOpen = action.catch(() => {});
  return action;
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (
    message?.type !== "get-veritascope-selection" ||
    !/^[a-f0-9-]{36}$/.test(message.id) ||
    !sender.url ||
    sender.frameId !== 0 ||
    new URL(sender.url).origin !== VERITASCOPE_ORIGIN
  ) {
    return;
  }

  const key = "selection:" + message.id;
  const storage = chrome.storage.session;
  if (message.consumed) {
    storage.remove(key).then(
      () => respond(true),
      () => respond(false),
    );
  } else {
    storage.get(key).then(
      (saved) => {
        const selection = saved[key];
        respond(
          selection && Date.now() - selection.createdAt <= SELECTION_TTL_MS
            ? selection
            : null,
        );
      },
      () => respond(null),
    );
  }
  return true;
});
