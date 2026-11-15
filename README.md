# Command-Editor

🇷🇺 [Русская версия](docs/ru/README.md)

A replacement for the **Commands** tab of Streamlabs Chatbot, for streamers still on **Windows 7** (or Linux).

A friend of mine is still on Windows 7, and his Streamlabs Chatbot stopped connecting to Twitch — so I wrote this. The code was written with an AI as an experiment, so some features may behave oddly. The past is the past; it works much better now.

> **Version 2.0 — beta (V2.0.0-Beta1).** What's new: [docs/release-notes.md](docs/release-notes.md).

---

## Features

**Commands**
- Reads Streamlabs Chatbot command backups (exporting back to Streamlabs is not supported)
- Sound and text (multi-line) commands, cooldowns (global and per viewer), a cost in points, volume
- Permissions: Everyone → Regular → Subscriber → VIP → Moderator → Admin
- Variables in responses: `{user}`, `{target}`, `{args}`, `{1}`…`{9}`, `{count}`, `{points}`, `{currency}`, `{channel}`, `{random:1-100}`
- Aliases: several names for one command (`!music, !tune`)
- A random sound from a folder (never the same one twice in a row)
- Auto-assign sounds from a folder by command name
- Test a command without Twitch: is the viewer allowed, do they have enough points, what goes to chat
- A trash for deleted commands, **Ctrl+Z** brings back the last one
- Search, save history, full backups

**Sound and queues**
- Queues per group: long sounds (music) do not cut each other off
- Volume per group and 32 audio channels: different groups play at the same time
- Optionally keep a group's queue across restarts
- Global hotkeys: skip, pause, "stop everything" — they work even in a game
- OBS overlay (Browser Source): what is playing, the queues, the latest commands

**Twitch and currency**
- Chat, viewers, active chatters, moderators, stream status; automatic reconnect
- Points for watching, Regular / Mod / Active bonuses, a multiplier for subscribers
- Raid and sub rewards (gift subs included), ranks by thresholds
- Timers: bot messages in chat every N minutes, only when the chat is active
- Statistics: popular commands, the points economy, top viewers

**Interface**
- Russian and English, the system language by default
- Four themes: Classic, Sidebar, Spreadsheet, Midnight (dark)
- Auto-save and protection against a second copy running with the same data folder

## System commands

| Command | Who | What it does |
|---|---|---|
| `!points` | everyone | show your points |
| `!add_points @user N` | mod | give points |
| `!remove_points @user N` | mod | take points |
| `!random` | everyone | a random command from a group |
| `!top` | everyone | top 5 by points |
| `!give @user N` | everyone | give some of your points to another viewer |
| `!uptime` | everyone | how long the stream has been live (and whether it is) |
| `!queue [GROUP]` | everyone | a group's queue / a summary of all queues |
| `!skip [GROUP]` | mod | stop the current sound (the shared channel or a group) |
| `!clear GROUP` | mod | empty a group's queue |
| `!volume [GROUP] <0-100>` | mod | a group's volume (the `SONG` group by default) |

## Requirements

- **Python 3.8** — the last Python for Windows 7; the versions in `requirements.txt`
  are pinned for it (twitchio 3.x needs Python 3.11+ and does not fit)
- The dependencies from `requirements.txt`: PyQt5, pygame, twitchio, aiohttp, requests and others

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/ColdDoshirak/Command-Editor.git
cd Command-Editor

# 2. A virtual environment (recommended)
python -m venv venv
# Windows: venv\Scripts\activate
# Linux:   source venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Run
python command_editor.py
```

The data (commands, settings, currency, backups) is kept next to the program. Set the
`COMMAND_EDITOR_HOME` environment variable to use another data folder.

## Building the .exe

```bash
pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm Command_Editor.spec   # -> dist/command_editor.exe
```

- The environment must not have the `pathlib` package (an outdated backport): with it
  PyInstaller refuses to build (`pip uninstall pathlib`).
- The spec builds a single file from `command_editor.py`; PyInstaller finds the `core/`,
  `bot/` and `ui/` packages by itself, the only data it needs is the `memes` folder.
- PyInstaller takes the UCRT (`ucrtbase.dll`, `api-ms-win-*.dll`) from `PATH`. For
  Windows 7 without update KB2999226 they must end up in the build — check
  `build/Command_Editor/EXE-00.toc`.

## Tests

```bash
python tests/run_tests.py      # offline: the bot, queues, data (~1 min)
python tests/ui/run_ui.py      # the real window, data in a temporary folder (~2 min)
```

## Quick start

1. **Export your commands** from Streamlabs Chatbot (right-click a command → *Export by group*).
2. In Command-Editor press **Load File**: the commands are loaded and converted to the new format.
3. **Twitch** tab: paste a token (from Twitch Token Generator, under the streamer's account; the scopes are listed in [docs/usage.md](docs/usage.md#twitch-tab-the-bot)), enter the channel, press **Connect**. On connect the program checks the token and says what is missing. You have to connect on every start.
4. **Group Settings** tab: turn on queues for the groups that need them and give them audio channels (for music, a `SONG` group with its own channel is recommended).
5. Optionally: **Settings** — theme, language, hotkeys, the OBS overlay; **Timers** — messages in chat; **Currency Settings** — points and rewards.
6. Done. The commands work in chat. To try a command without a stream, use the **Test…** button.

## Documentation

- [docs/usage.md](docs/usage.md) — every tab and setting
- [docs/features.md](docs/features.md) — each feature in detail: variables, aliases, permissions, timers, the overlay, hotkeys, the token
- [docs/queue.md](docs/queue.md) — queues: groups, channels, commands, persistence
- [docs/release-notes.md](docs/release-notes.md) — what changed in 2.0
- [docs/ru/](docs/ru/README.md) — the same in Russian

## Known issues

- Follow rewards are not paid: Twitch does not report follows through chat
  (they will come with EventSub). Raid and sub rewards work.
- The token is taken by hand from Twitch Token Generator and does not refresh by itself:
  when it expires you need a new one (the program warns you on Connect when it is about
  to expire). Logging in with Twitch from inside the program is planned.
- Commands without `!` do not trigger.
- You have to connect to Twitch on every start.

---

*Made in 2025–2026 with an AI. Yes, it's shitcode. Yes, it works. Fork it and fix it — PRs are welcome.*
