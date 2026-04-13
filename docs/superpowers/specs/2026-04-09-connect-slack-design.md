# Connect Slack to Rei — Design Spec

**Date:** 2026-04-09  
**Scope:** Configuration setup + code changes to `nanobot/channels/slack.py` for inbound file handling.

---

## Summary

Connect the Slack messaging channel to the rei agent by configuring `~/.nanobot/config.json` and updating `nanobot/channels/slack.py` to support inbound image/audio file downloading and transcription.

`slack-sdk` and `slackify-markdown` are already in `pyproject.toml`. Tests pass.

---

## Approach

Socket Mode only. HTTP webhook mode is not implemented.

---

## Steps

### 1. Create a Slack App

At https://api.slack.com/apps, create a new app ("From scratch").

**Settings → Socket Mode:** Enable, generate an App-Level Token with scope `connections:write`. Copy the `xoxapp-...` value.

**OAuth & Permissions → Bot Token Scopes:** Add:
- `chat:write`
- `files:read`
- `files:upload`
- `reactions:add`
- `reactions:remove`
- `channels:history`
- `groups:history`
- `im:history`
- `mpim:history`
- `app_mentions:read`

Install the app to workspace → copy the `xoxb-...` Bot Token.

**Event Subscriptions → Subscribe to bot events:**
- `message.im` (DMs)
- `app_mention` (@ mentions in channels)

### 2. Get Your Slack User ID

In Slack: click your profile → three-dot menu → **Copy member ID** (format: `U01XXXXXXXX`).

### 3. Add to ~/.nanobot/config.json

Add to the `channels` object:

```json
"slack": {
  "enabled": true,
  "botToken": "xoxb-your-bot-token",
  "appToken": "xoxapp-your-app-token",
  "allowFrom": ["your-slack-user-id"],
  "replyInThread": true,
  "reactEmoji": "eyes",
  "doneEmoji": "white_check_mark"
}
```

---

## Configuration Reference

| Field | Default | Notes |
|---|---|---|
| `botToken` | `""` | `xoxb-...` from OAuth & Permissions |
| `appToken` | `""` | `xoxapp-...` from Socket Mode |
| `allowFrom` | `[]` | Slack User IDs allowed to talk to rei; `["*"]` = everyone |
| `replyInThread` | `true` | Reply in thread for channel messages |
| `reactEmoji` | `"eyes"` | Reaction added while processing |
| `doneEmoji` | `"white_check_mark"` | Reaction added when done |
| `groupPolicy` | `"mention"` | Channel behavior: `"mention"` = respond only when @mentioned |
| `dm.enabled` | `true` | Allow DMs |
| `dm.policy` | `"open"` | `"open"` = all users; `"allowlist"` = only `dm.allowFrom` |
