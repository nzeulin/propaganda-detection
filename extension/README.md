# Open in VeritasScope

This Manifest V3 demo opens the team's VeritasScope site and fills its content
analysis text box with the text you select. The team demo uses the existing
[Hostinger site](http://153.92.222.180:8080/). The extension leaves submission
to the site's **Analyze** button.

## Install in Chrome or Edge

1. Download and extract the demo ZIP, or use this `extension/` folder from
   the repository.
2. Open `chrome://extensions` or `edge://extensions`.
3. Turn on **Developer mode**, choose **Load unpacked**, and select the folder
   containing `manifest.json`.
4. Highlight text on a web page, right-click it, then choose
   **Open in VeritasScope**. The text appears in the analysis field in a new tab.

The extension reads the selection when you click its menu item. It uses
extension session storage to pass it to the new tab and removes the entry after
filling the form. The URL briefly includes a random token. The content script
runs on the demo site and checks its exact origin before requesting a selection.
The destination currently uses HTTP. Use public sample text for the demo.

Selections above the site's 40,000-character limit are shortened with a notice.
The extension does not need a provider API key.
