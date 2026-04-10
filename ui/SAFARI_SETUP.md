# Safari Web Extension Setup — CoworkSafari

## Current Status

The Safari Web Extension conversion has **not yet been completed** due to a missing prerequisite.

### Exact Error

```
xcrun: error: unable to find utility "safari-web-ext-converter", not a developer tool or in PATH
```

### Why It Failed

Only the **Xcode Command Line Tools** are installed on this machine:

```bash
xcode-select -p
# Returns: /Library/Developer/CommandLineTools
```

The `safari-web-ext-converter` tool ships **exclusively** inside the full **Xcode.app** — it is
not part of the standalone Command Line Tools package. There is no workaround; the full Xcode
application must be installed.

---

## Fix: Install Full Xcode

1. Open the **App Store** on your Mac.
2. Search for **Xcode** (published by Apple, free, approximately 7 GB).
3. Click **Get / Install** and wait for the full download and installation to complete.
4. Launch Xcode once after installation to accept the license agreement and install any
   additional components when prompted. Do not skip this step.
5. Switch the active developer directory to the full Xcode:
   ```bash
   sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
   ```
6. Verify it is active:
   ```bash
   xcode-select -p
   # Should print: /Applications/Xcode.app/Contents/Developer
   ```

---

## Step 1: Convert the Chrome Extension

Once Xcode is installed, run this exact command from your terminal:

```bash
xcrun safari-web-ext-converter ~/cowork/ui/chrome-extension \
  --project-location ~/cowork/ui/ \
  --app-name CoworkSafari \
  --bundle-identifier com.cowork.safari \
  --swift \
  --force
```

This generates a new Xcode project at:

```
~/cowork/ui/CoworkSafari/
  CoworkSafari.xcodeproj         ← Xcode project file
  CoworkSafari/                  ← macOS app wrapper (Swift)
  CoworkSafari Extension/        ← Web extension resources (copied from chrome-extension/)
```

Open the project in Xcode:

```bash
open ~/cowork/ui/CoworkSafari/CoworkSafari.xcodeproj
```

---

## Step 2: Build in Xcode with a Free Apple ID

You do **not** need a paid Apple Developer account to run the extension locally. A free Apple ID
is sufficient.

1. Open `CoworkSafari.xcodeproj` in Xcode.
2. In the **Project Navigator** (left sidebar), click the top-level **CoworkSafari** project item.
3. Select the **CoworkSafari** target (the macOS app wrapper, not the extension target).
4. Open the **Signing & Capabilities** tab.
5. Check **Automatically manage signing**.
6. Under **Team**, select your personal Apple ID:
   - If it is not listed, click **Add an Account...** (Xcode menu → Preferences → Accounts)
     and sign in with any Apple ID. A free account creates a "Personal Team".
   - Select the entry shown as **Your Name (Personal Team)**.
7. Xcode will automatically create a free provisioning profile.
8. Repeat steps 3–7 for the **CoworkSafari Extension** target.
9. In the toolbar at the top of Xcode, set the run destination to **My Mac**.
10. Press **Cmd+R** (or click the Run triangle) to build and run.
    - A small wrapper app will launch briefly. You can quit it immediately — its sole purpose
      is to install the extension into Safari.

> **Important:** Free Apple ID provisioning profiles expire after **7 days**. After expiry the
> extension will be disabled by Safari. Rebuild and re-run from Xcode to renew the signature.

---

## Step 3: Enable the Develop Menu and Allow Unsigned Extensions

Safari blocks unsigned extensions by default. To allow them during development:

1. Open **Safari**.
2. Go to **Safari → Settings** (macOS Ventura+) or **Safari → Preferences** (older macOS).
3. Click the **Advanced** tab.
4. Check **Show features for web developers**. This makes the Develop menu appear in the menu bar.
5. In the menu bar, click **Develop**.
6. Click **Allow Unsigned Extensions**.
   - macOS will prompt for your login password.
   - This setting **resets every time Safari quits**. You must re-enable it each time you
     restart Safari during development.

---

## Step 4: Enable the Extension and Allow Access to All Websites

1. Go to **Safari → Settings → Extensions**.
2. Find **CoworkSafari** in the list and check its checkbox to enable it.
3. Click **Always Allow on Every Website** when the permission prompt appears.
   - If that button does not appear, click the extension icon in the Safari toolbar, then grant
     permissions from the dropdown.

---

## Step 5: Reloading the Extension During Development

Safari Web Extensions do not hot-reload. To pick up changes to the extension source files:

1. Edit your files in `~/cowork/ui/chrome-extension/` as normal.
2. In Xcode, press **Cmd+R** to rebuild and re-run the app.
3. Back in Safari:
   - Re-enable **Develop → Allow Unsigned Extensions** if Safari was restarted.
   - Go to **Settings → Extensions**, uncheck then re-check **CoworkSafari** to reload it.
   - Reload any tabs the extension acts on (Cmd+R in the tab).

---

## Compatibility Notes

The Cowork Chrome extension uses **Manifest V3**, which Safari 16+ supports. However, some
Chrome-specific APIs are not available in Safari:

| Feature | Chrome | Safari |
|---|---|---|
| `chrome.offscreen` | Supported | **Not supported** |
| `chrome.*` namespace | Native | Supported via polyfill (added automatically by Xcode) |
| WebSocket in service worker | Via offscreen doc | Limited — use keepAlive alarms |
| Notifications | `chrome.notifications` | Requires macOS permission prompt |

### Offscreen API Workaround for Safari

The extension currently uses `chrome.offscreen` to maintain persistent WebSocket connections.
Safari does not support this API. The converter will flag it. Replace the offscreen approach
with direct WebSocket management in the background service worker, kept alive with periodic
alarms:

```js
// In background.js — replace ensureOffscreen() with direct WebSocket management.
// Keep the service worker alive in Safari using alarms:
chrome.alarms.create('keepalive', { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => { /* no-op, prevents SW termination */ });
```

---

## Alternative Approaches (If You Cannot Install Xcode)

### Option A: Safari Technology Preview (No Xcode Wrapper Needed)

Safari Technology Preview (free download from Apple) supports loading unpacked extensions
directly from disk, similar to Chrome's developer mode:

1. Download Safari Technology Preview from:
   https://developer.apple.com/safari/technology-preview/
2. Open it, go to **Develop → Allow Unsigned Extensions**.
3. Go to **Settings → Extensions → Developer Extensions** and load the unpacked extension.

This is the fastest path for pure JavaScript/CSS/HTML development without any Xcode involvement.

### Option B: Firefox (Full WebExtension API Compatibility)

The Cowork extension uses standard WebExtension APIs that Firefox supports with no changes:

1. Open Firefox and navigate to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on...**
3. Select `~/cowork/ui/chrome-extension/manifest.json`.
4. The extension loads immediately and stays active until Firefox is restarted.

This is a practical alternative browser target while Safari/Xcode support is being set up.

---

## Summary Checklist

- [ ] Install full **Xcode** from the Mac App Store (~7 GB)
- [ ] Launch Xcode once to accept the license and install components
- [ ] Run `sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer`
- [ ] Run the `xcrun safari-web-ext-converter` command above
- [ ] Open `~/cowork/ui/CoworkSafari/CoworkSafari.xcodeproj` in Xcode
- [ ] Set signing team to your personal Apple ID for both targets (app + extension)
- [ ] Build and run with **Cmd+R** (destination: My Mac)
- [ ] Safari: enable Develop menu via Settings → Advanced → Show features for web developers
- [ ] Safari: Develop → Allow Unsigned Extensions (re-enable each Safari session)
- [ ] Safari: Settings → Extensions → enable CoworkSafari → Always Allow on Every Website
