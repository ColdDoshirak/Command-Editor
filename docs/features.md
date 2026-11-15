# Features in detail

🇷🇺 [Русская версия](ru/features.md)

How each feature of Command Editor 2.0 works and how to set it up. This page covers only the features; an overview of all tabs is in [usage.md](usage.md), queues are in [queue.md](queue.md).

Button names are given as they appear in the English interface.

**Contents**

- [Command responses](#command-responses)
- [Variables in responses](#variables-in-responses)
- [Aliases](#aliases)
- [Command permissions](#command-permissions)
- [A random sound from a folder](#a-random-sound-from-a-folder)
- [Testing a command without Twitch](#testing-a-command-without-twitch)
- [The trash and Ctrl+Z](#the-trash-and-ctrlz)
- [Timers](#timers)
- [Statistics](#statistics)
- [OBS overlay](#obs-overlay)
- [Global hotkeys](#global-hotkeys)
- [Twitch token check](#twitch-token-check)
- [Language and themes](#language-and-themes)
- [Where things are stored](#where-things-are-stored)

---

## Command responses

The **Response** field is what the bot writes to chat when the command runs.

- **Each line is a separate message** in chat. The lines go out one after another with a short pause, so Twitch does not treat them as spam.
- **An empty line is a pause** of about 0.2 seconds before the next line.
- [Variables](#variables-in-responses) work in a response: `{user}`, `{target}` and others.
- A response can be combined with a sound: the command both writes to chat and plays the file.

A response of three messages:

```
Hi, {user}!

Today we play {args}
```

If you write `!hello Factorio`, the bot sends "Hi, alice!", waits a moment and sends "Today we play Factorio".

---

## Variables in responses

A variable is a word in curly braces that the bot replaces when it sends the message.

| Variable | What it becomes | `!hug @Bob tightly` by alice |
|---|---|---|
| `{user}` | who called the command | `alice` |
| `{target}` | the first word after the command, without `@`; with no words — the viewer themselves | `Bob` |
| `{args}` | everything written after the command | `@Bob tightly` |
| `{1}` … `{9}` | one word after the command by its number, as written (with `@`) | `{1}` = `@Bob`, `{2}` = `tightly` |
| `{count}` | how many times the command has run, this time included | `5` |
| `{points}` | the points of the viewer who called the command | `120` |
| `{currency}` | the currency name from Currency Settings | `points` |
| `{channel}` | the channel | `hotdoshirak` |
| `{random:1-100}` | a random whole number in the range, both ends included | `42` |

Examples:

- `{user} hugs {target}! Hugs on this channel: {count}` → "alice hugs Bob! Hugs on this channel: 5".
- `{user} rolls a die: {random:1-6}` → "alice rolls a die: 4".
- `{user} has {points} {currency}`.

Details:

- Case does not matter: `{User}` and `{USER}` work too.
- If there is no word after the command, `{1}` becomes empty and `{target}` becomes the viewer's own name. So for "doing something to someone" `{target}` is the handier one.
- Anything unknown in curly braces (`{abc}`, `{random:x}`, a piece of JSON) stays as written. Old responses with braces do not break.
- Negative numbers work: `{random:-10-10}`. If the ends are swapped (`{random:10-1}`), the bot swaps them back.
- In [timers](#timers) only `{channel}` and `{random:…}` work: there is no viewer who called them.
- [Test…](#testing-a-command-without-twitch) shows how a response looks with the values filled in.

---

## Aliases

An alias is another name of the same command. `!music`, `!tune` and `!song` can all call one command.

**Where to set them**

- **Classic theme:** the Commands tab, select a command, the **Aliases** field in the panel under the table, in the left column after the description. It is saved when you leave the field: Tab, Enter or a click elsewhere.
- **Sidebar, Spreadsheet, Midnight themes:** select a command, the **Aliases** field in the card on the right, under Info. It is saved as you type.

**Format:** names separated by commas, spaces or `;`. The exclamation mark and case do not matter: `!music, tune  !Track` gives three aliases — `music`, `tune`, `track`.

**How they work**

- An alias calls **the very same** command: a shared cooldown, the same cost, the same `{count}` counter.
- The table has no column for them: aliases are stored in the command's `Aliases` field in `commands.json`.
- To check an alias, use **Test…**: write `!tune` in it instead of the main name.

---

## Command permissions

The **Permission** field — who may call the command. The levels form a ladder, and each one includes all the lower ones:

**Everyone → Regular → Subscriber → VIP → Moderator → Admin**

A Subscriber command can be called by a subscriber, a VIP, a moderator and an admin, but not by an ordinary viewer or a regular.

| Level | Where the program learns it |
|---|---|
| **Everyone** | everyone |
| **Regular** | the Regular status in the currency: given automatically by points or hours (Currency Settings) or by hand on the Currency Users tab |
| **Subscriber** | the subscriber badge on the chat message |
| **VIP** | the VIP badge |
| **Moderator** | the moderator badge, the channel's moderators from Twitch and the manual list |
| **Admin** | the channel owner, the `admins` list in `moderators.json` and — by default — all moderators |

**Moderators and Admin.** By default, as in 1.x, a moderator may call Admin commands too. To keep Admin commands to yourself and trusted people, turn off **Settings → Permissions → Moderators have Admin rights**. Then Admin is the channel owner and the names in the `admins` list.

**The manual lists** are in `moderators.json`. Open it with the **Open moderators file** button on the Twitch tab:

- `manual_moderators` — who counts as a moderator even if Twitch does not say so;
- `excluded_moderators` — who loses moderator rights (an Admin given through `admins` is not affected);
- `admins` — who counts as Admin.

The moderators list on the Twitch tab shows where each one comes from: `[Twitch]`, `[Manual]`, `[Both]`, `[Excluded]`, `[Admin]`.

Details:

- The channel owner may call any command.
- Subscribers and VIPs are recognised only by the badges on their message: the program has no other source.
- Names from Streamlabs exports (`Regular`, `Subscriber`, `Mod`, `Caster` and so on) are understood automatically.

---

## A random sound from a folder

Instead of a single file you can give a command a folder: each call plays a random sound from it.

**How to set it up:** the **Folder…** button next to the file picker (Browse or the folder icon) — pick the folder with the sounds. The sound field then shows the folder path.

- `.wav`, `.mp3`, `.ogg` and `.flac` files are used; other files in the folder are ignored. Subfolders are not searched.
- The same sound never plays twice in a row if the folder has more than one file.
- Files can be added and removed without restarting the program: the folder is read on every call.
- If the folder has no sounds, the command runs without a sound.
- Volume, queue and the group's channel work the same as with a single file.

---

## Testing a command without Twitch

The **Test…** button shows what would happen if a viewer wrote a message. No connection to Twitch is needed.

**Where:** in the classic theme — next to Play in the command panel; in the themes — in the command card, and in Spreadsheet also on the toolbar.

**What to fill in**

- **Message in chat** — the whole message, for example `!hug @Bob`;
- **Viewer** — the viewer's name (for `{user}`);
- **Viewer is** — their level: Everyone, Regular, Subscriber, VIP, Moderator or Admin;
- **Viewer's points** — how many points they have.

**What it shows**

- whether the message calls this command, aliases included;
- whether the command is enabled;
- whether a viewer of that level is allowed;
- whether they have enough points;
- which messages go to chat, with the variables filled in;
- whether the sound file exists. **Play the sound** lets you listen to it right away.

It is a dry run: no points are taken, no cooldown starts, the counter does not change.

---

## The trash and Ctrl+Z

A deleted command is not lost; it goes to the trash.

- **Ctrl+Z** puts the last deleted command back in its place. Inside a text field Ctrl+Z undoes typing, as usual.
- **Trash…** shows every deleted command, newest first. **Restore** brings back the selected one, **Empty the trash** clears the trash for good. In the themes the trash opens from the "…" menu.
- The trash keeps the last 50 commands; older ones are dropped.
- The trash survives a restart: it is in `command_trash.json` next to `commands.json`.

---

## Timers

Messages the bot writes to chat by itself: a follow reminder, links, rules.

**Where:** the **Timers** tab. **Add timer** adds a row; every change is saved at once and picked up by the running bot without reconnecting.

| Column | Meaning |
|---|---|
| **On** | the timer is on |
| **Message** | the message text |
| **Every (min)** | how often, in minutes (at least 1) |
| **After chat lines** | how many chat messages must appear since the last time; 0 — do not wait |
| **Live only** | write only while the stream is live |

A timer writes when **all** conditions are met: N minutes have passed, at least M messages appeared in chat (so the bot does not talk to itself in an empty chat), and — with Live only — the stream is live.

Also worth knowing:

- The first message comes one interval after the bot connects, not at once.
- If you change a timer's text, its countdown starts over.
- **Post now** sends the selected message at once, without waiting for the interval. The bot must be connected.
- `{channel}` and `{random:1-100}` work in the text.
- A long message is cut to Twitch's limit (500 characters) and always goes out as one line.
- Live only needs a working token (see [the token check](#twitch-token-check)): without it the program does not know whether the stream is live.

A new timer by default: every 15 minutes, after 5 chat messages, only while live.

---

## Statistics

**Where:** the **Stats** tab. Pick the period at the top: Today, 7, 30 or 90 days. The data refreshes every 30 seconds and with the **Refresh** button.

**Points for the period**

- **Earned by watching** — given for watch time;
- **Raid / sub rewards** — given for raids and subs;
- **Spent on commands** — spent on commands (refunds for sounds that did not play are subtracted);
- **Given between viewers** — moved with `!give`.

**Right now**

- **Held by viewers now** — how many points all viewers hold together;
- **Viewers in the system** — how many viewers the currency knows;
- **Chatting now (10 min)** — how many people wrote in chat in the last 10 minutes.

**Tables:** popular commands (for the period and for all time), top viewers by points and by hours.

The daily counters are in `stats.json` and are kept for 90 days. Statistics start from the day 2.0 was installed, so there is none for earlier.

---

## OBS overlay

A small web page for OBS: what is playing now, the queues and the latest commands with the viewers. Its background is transparent.

**How to turn it on**

1. **Settings → OBS overlay**: turn on **Enable the overlay**. The default port is 8765.
2. Press **Copy** next to the address: `http://127.0.0.1:8765/`.
3. In OBS: **Sources → + → Browser**, paste the address. A handy size is 400 wide, 600 high.

**Options in the address**

- `?show=now,queue,recent` — which blocks to show: `now` — what is playing, `queue` — the queues, `recent` — the latest commands. All three by default.
- `&size=28` — the font size in pixels (22 by default).

For example, only "now playing" in a big font: `http://127.0.0.1:8765/?show=now&size=32`.

Details:

- The page refreshes once a second.
- "Recent" holds the last 10 calls.
- The overlay works without a connected bot too; it just shows empty blocks.
- The page opens only on this computer (the address is 127.0.0.1); another device on the network cannot open it.
- If the port is taken by another program, the card says so — pick another one and update the address in OBS.

---

## Global hotkeys

Control the sound while the window is minimised or a game has the focus.

**Where:** **Settings → Global hotkeys**, the **Enable global hotkeys** switch. Off by default: while they are on, these key combinations are captured and do not reach other programs.

| Action | Default | What it does |
|---|---|---|
| Skip what is playing | Ctrl+Alt+S | skips what is playing now in every queue; if the queues are silent, stops the sound on the shared channel |
| Pause / resume the queues | Ctrl+Alt+P | pauses every queue (the playing sound finishes) or, if all are paused already, resumes them |
| Stop all sounds and pause the queues | Ctrl+Alt+M | silences every sound at once and pauses the queues — the "panic button". Resume with Ctrl+Alt+P |

- To change a combination, click its field and press the new keys.
- If a combination is already taken by another program, the card says so — pick another one.
- The bot carries out the actions, so the queues obey the keys only while the bot is connected. Without the bot, Skip and Stop just silence the sound in the program itself.
- Every press is noted in the Twitch tab's chat as a `[Hotkey] …` line.
- Global hotkeys work only on Windows.
- The chat commands (`!skip` and others) work independently of the hotkeys.

---

## Twitch token check

When you press **Connect**, the program first asks Twitch about the token it has and writes the result to the Twitch tab's chat.

**What it reports**

- whose token it is and when it expires (with a separate warning if less than a week is left);
- if the token is **not the channel owner's** — that the list of all viewers and the moderators will be incomplete;
- which **scopes** (token permissions) are missing and what will not work without them;
- if the token expired or was revoked — the connect stops and the program shows a window explaining why.

You do not need to enter the **Client ID**: the program takes it from Twitch's answer and saves it.

**Which token you need.** Generate it on [Twitch Token Generator](https://twitchtokengenerator.com/) under the **streamer's** account and tick these scopes:

| Scope | Without it there is no |
|---|---|
| `chat:read` | reading the chat |
| `chat:edit` | bot answers and timers |
| `moderator:read:chatters` | list of all viewers — only viewers who chat earn points for watching |
| `moderation:read` | moderators list from Twitch — only badges in chat are seen |

With a token of a separate bot account the list of all viewers and the moderators do not work even with every scope: Twitch gives them only with the channel owner's token.

The token does not refresh by itself. When it expires, get a new one and enter it in **Authenticate**.

---

## Language and themes

**Language:** **Settings → Language** — System (default), Русский or English. System means Russian on a Russian Windows and English on any other. The language changes after the program restarts.

Not translated:

- the bot's answers in chat — you write their text;
- the values stored in files: permissions (`Everyone`, `Moderator`), where a command works (`SC`, `Chat`, `Both`), group names;
- the bot's service lines in the Twitch tab's chat ("Connected to…").

**Themes:** **Settings → Appearance** or the drop-down on the About tab. They change at once, without a restart.

| Theme | What it is |
|---|---|
| **Classic** | Windows-style tabs, the commands table with a panel under it |
| **Sidebar** | a menu on the left, the commands list and a command card |
| **Spreadsheet** | a dense commands table for long lists |
| **Midnight** | dark, for streaming at night |

---

## Where things are stored

All files are next to the program (or in the folder from the `COMMAND_EDITOR_HOME` environment variable).

| File | What it holds |
|---|---|
| `commands.json` | the commands, aliases (`Aliases`) included |
| `command_trash.json` | the trash of deleted commands |
| `config.json` | settings: groups, timers, hotkeys, the overlay, language, theme |
| `twitch_config.json` | the token, Client ID, refresh token — never share this file |
| `moderators.json` | manual moderators, excluded ones, `admins`, "Moderators have Admin rights" |
| `users_currency.json` | the viewers' points and hours |
| `stats.json` | statistics by day (90 days) |
| `backups/` | backups of commands and currency, and full backups (without the token) |
| `command_editor.log`, `command_editor_crash.log` | the work and crash logs — attach them to a bug report |
