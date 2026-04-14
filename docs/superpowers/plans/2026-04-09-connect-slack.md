# Connect Slack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Slack as an active channel in rei's `~/.nanobot/config.json` and extend `SlackChannel` to handle inbound image/audio files.

**Architecture:** Two parts: (1) configuration — `~/.nanobot/config.json` needs a new `slack` section; `ChannelManager` auto-discovers and loads the channel on startup. (2) code — `nanobot/channels/slack.py` requires changes to download inbound `files[]` with Bearer-auth, transcribe audio via `transcribe_audio()`, and pass local paths to `_handle_message(media=[...])`.

**Tech Stack:** slack-sdk (Socket Mode), slackify-markdown — both already installed.

---

### Task 1: Create Slack App and Collect Tokens

**Files:**
- No file changes — external Slack setup step.

- [ ] **Step 1: Create the Slack App**

  Go to https://api.slack.com/apps → **Create New App** → **From scratch**.
  Name: `rei` (or any name). Select your workspace.

- [ ] **Step 2: Enable Socket Mode and generate App-Level Token**

  Left sidebar → **Socket Mode** → Enable.
  Click **Generate an app-level token** → name it `socket` → add scope `connections:write` → **Generate**.
  Copy the token (starts with `xoxapp-`). Save it.

- [ ] **Step 3: Add Bot Token Scopes**

  Left sidebar → **OAuth & Permissions** → **Bot Token Scopes** → Add:
  - `chat:write`
  - `files:read`
  - `files:write`
  - `reactions:add`
  - `reactions:remove`
  - `channels:history`
  - `groups:history`
  - `im:history`
  - `mpim:history`
  - `app_mentions:read`

- [ ] **Step 4: Subscribe to Events**

  Left sidebar → **Event Subscriptions** → Enable Events.
  Under **Subscribe to bot events**, add:
  - `message.im`
  - `app_mention`

  Save Changes.

- [ ] **Step 5: Install App to Workspace**

  Left sidebar → **OAuth & Permissions** → **Install to Workspace** → Allow.
  Copy the **Bot User OAuth Token** (starts with `xoxb-`). Save it.

- [ ] **Step 6: Get your Slack User ID**

  In the Slack desktop/web app: click your name → **Profile** → three-dot menu (⋯) → **Copy member ID**.
  It looks like `U01XXXXXXXX`. Save it.

---

### Task 2: Add Slack Config to ~/.nanobot/config.json

**Files:**
- Modify: `~/.nanobot/config.json` — add `"slack"` key inside `"channels"`

- [ ] **Step 1: Open config**

  ```bash
  nano ~/.nanobot/config.json
  ```

- [ ] **Step 2: Add slack section inside the `"channels"` object**

  Find the `"channels"` block (it already has `"telegram"` and `"weixin"`). Add `"slack"` alongside them:

  ```json
  "channels": {
    "sendProgress": true,
    "sendToolHints": false,
    "telegram": { ... },
    "weixin": { ... },
    "slack": {
      "enabled": true,
      "botToken": "xoxb-YOUR-BOT-TOKEN",
      "appToken": "xoxapp-YOUR-APP-TOKEN",
      "allowFrom": ["U01XXXXXXXX"],
      "replyInThread": true,
      "reactEmoji": "eyes",
      "doneEmoji": "white_check_mark"
    }
  }
  ```

  Replace:
  - `xoxb-YOUR-BOT-TOKEN` with your Bot User OAuth Token from Task 1 Step 5
  - `xoxapp-YOUR-APP-TOKEN` with your App-Level Token from Task 1 Step 2
  - `U01XXXXXXXX` with your Slack User ID from Task 1 Step 6

- [ ] **Step 3: Validate JSON is well-formed**

  ```bash
  python3 -m json.tool ~/.nanobot/config.json > /dev/null && echo "JSON valid" || echo "JSON INVALID — fix syntax"
  ```

  Expected output: `JSON valid`

---

### Task 3: Verify Slack Channel Loads

**Files:**
- No changes — verification only.

- [ ] **Step 1: Restart rei gateway**

  ```bash
  pkill -f "nanobot" 2>/dev/null; sleep 1
  nanobot
  ```

  Or if you use `start-gateway.sh`:

  ```bash
  ~/.nanobot/start-gateway.sh
  ```

- [ ] **Step 2: Confirm Slack channel appears in startup logs**

  Look for this line in the output:
  ```
  Slack channel enabled
  ```
  And shortly after:
  ```
  Slack bot connected as U...
  Starting Slack Socket Mode client...
  ```

  If you see `Slack bot/app token not configured` — re-check `botToken`/`appToken` in config.json.

- [ ] **Step 3: Send a test DM to rei in Slack**

  Open Slack → find the rei bot in Apps → send a DM: `hello`.

  Expected: rei replies (possibly with :eyes: reaction first, then :white_check_mark: when done).

  If no response:
  - Check that your Slack User ID in `allowFrom` matches exactly (`U01XXXXXXXX` is case-sensitive)
  - Check gateway logs for `Access denied for sender ...`
  - Check that Event Subscriptions has `message.im` added (Task 1 Step 4)
