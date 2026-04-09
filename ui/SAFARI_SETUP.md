# Safari Web Extension Setup — Jarvis

## Status

The `safari-web-extension-converter` tool requires **Xcode.app** (full IDE, not just Command Line Tools).
Only Xcode Command Line Tools were found on this machine — the converter is not available.

### xcrun output
```
xcrun: error: unable to find utility "safari-web-ext-converter", not a developer tool or in PATH
```

---

## How to convert (when Xcode is installed)

### 1. Install Xcode from the Mac App Store
https://apps.apple.com/us/app/xcode/id497799835

### 2. Run the converter
```bash
xcrun safari-web-extension-converter \
  ~/cowork/ui/chrome-extension \
  --project-location ~/cowork/ui/ \
  --app-name JarvisSafari \
  --bundle-identifier com.cowork.jarvis \
  --swift
```

This generates `~/cowork/ui/JarvisSafari/` containing:
- `JarvisSafari.xcodeproj` — Xcode project
- `JarvisSafari/` — macOS app wrapper
- `JarvisSafari Extension/` — the web extension resources (copied from chrome-extension/)

### 3. Open the Xcode project
```bash
open ~/cowork/ui/JarvisSafari/JarvisSafari.xcodeproj
```

### 4. Set signing to "Sign to Run Locally"
1. Click the **JarvisSafari** project in the Project Navigator (left panel)
2. Select the **JarvisSafari** target (not the Extension target)
3. Go to the **Signing & Capabilities** tab
4. Under **Signing**, set **Team** to `None`
5. Check **Automatically manage signing**
6. When prompted, choose **Sign to Run Locally**
7. Repeat for the **JarvisSafari Extension** target

### 5. Build and run
Press `Cmd+R` or click the Run button. This launches the macOS wrapper app.

### 6. Enable the extension in Safari
1. Open **Safari**
2. Go to **Safari > Settings** (or Preferences on older macOS)
3. Click the **Extensions** tab
4. Find **JarvisSafari** and check the checkbox to enable it
5. Click **Always Allow on Every Website** when prompted (required for content scripts)

### 7. Allow unsigned extensions (if needed)
If Safari shows a warning about developer extensions:
1. Go to **Safari > Settings > Advanced**
2. Check **Show Develop menu in menu bar**
3. Open the **Develop** menu
4. Click **Allow Unsigned Extensions**
5. This must be re-enabled each time Safari is relaunched

---

## Compatibility notes

The Jarvis Chrome extension uses **Manifest V3** which Safari 16+ supports.

### Known differences between Chrome and Safari Web Extensions

| Feature | Chrome | Safari |
|---|---|---|
| Offscreen API | Supported | Not supported — use `browser.runtime.sendNativeMessage` or a background page instead |
| `chrome.*` namespace | Native | Supported via polyfill (Xcode project includes it automatically) |
| WebSocket in service worker | Via offscreen doc | Limited — may need native app bridge |
| Notifications | `chrome.notifications` | Requires macOS permission prompt |

### Offscreen API workaround for Safari
The extension currently uses `chrome.offscreen` to maintain WebSocket connections in a persistent
document. Safari does not support this API. The converter will flag this. Replace the offscreen
approach with a **native messaging host** or keep WebSockets in the background service worker
with `keepAlive` heuristics:

```js
// In background.js, replace ensureOffscreen() with direct WebSocket management
// Safari service workers can be kept alive with periodic alarms:
chrome.alarms.create('keepalive', { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => { /* no-op, keeps SW alive */ });
```

---

## Quick reference: enable in Safari (summary)
1. Build and run from Xcode (`Cmd+R`)
2. Safari > Settings > Extensions > enable JarvisSafari
3. Develop > Allow Unsigned Extensions (each relaunch)
4. Click the extension icon in the toolbar to open the popup
