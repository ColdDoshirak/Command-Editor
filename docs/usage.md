# User guide

🇷🇺 [Русская версия](ru/usage.md)

Every tab and setting of Command-Editor. The short version is in the [README](../README.md).

## Working with commands

- **Export from Streamlabs.** In Streamlabs Chatbot export your commands (right-click a command → *Export by group* is the handiest). If you have several groups, one at a time is safer: importing several groups at once has not been tested.
- **Load File** — load commands from a backup. A new file in the new format is created after loading.
- **Save File** — save the commands to a file. They are also saved automatically every 300 seconds and when the program closes.
- **Save Legacy Format** — save in the old format. *Not recommended*: it causes incompatibilities with Streamlabs Chatbot.
- **Auto-Assign Sounds** — assign sound files automatically. Pick a folder with sounds; it only works when the names match (`!command` → `!command.mp3`/`.wav`).
- **Add / Remove Command** — add a command / delete the selected one. A deleted
  command goes to the trash: **Ctrl+Z** puts the last one back in its place,
  **Trash…** (in the themes — the "…" menu) shows every deleted command (up to 50).
- **Play Sound** — play / stop a command's sound. Works even while the bot is connected.
- **Allow sounds to interrupt each other** — let sounds cut each other off (or not).
- **Show message when sound blocked** — a warning when a sound did not play because another one was still playing.
- **Search** — search by command name.
- **History** — the save history. Keep plenty of backups.

### Command features

In detail, with examples, in [features.md](features.md):

- [Responses](features.md#command-responses): each line is a separate message, an empty line is a pause.
- [Variables](features.md#variables-in-responses): `{user}`, `{target}`, `{args}`, `{1}`…`{9}`, `{count}`, `{points}`, `{currency}`, `{channel}`, `{random:1-100}`.
- [Aliases](features.md#aliases): the **Aliases** field, other names of the same command.
- [Permissions](features.md#command-permissions): Everyone → Regular → Subscriber → VIP → Moderator → Admin.
- [A random sound from a folder](features.md#a-random-sound-from-a-folder): the **Folder…** button.
- [Test…](features.md#testing-a-command-without-twitch): what a command would do, without Twitch.
- [The trash and Ctrl+Z](features.md#the-trash-and-ctrlz): deleted commands can be brought back.

Separate tabs and settings: [timers](features.md#timers), [statistics](features.md#statistics), [the OBS overlay](features.md#obs-overlay), [hotkeys](features.md#global-hotkeys), [the token check](features.md#twitch-token-check), [language and themes](features.md#language-and-themes).

## Twitch tab (the bot)

- Connecting to a channel: **Channel** + **Connect**.
- The **token** comes from [Twitch Token Generator](https://twitchtokengenerator.com/) and goes into **Authenticate**. Generate it under the **streamer's** account and tick these scopes:

  | Scope | Without it there is no |
  |---|---|
  | `chat:read` | reading the chat |
  | `chat:edit` | bot answers and timers |
  | `moderator:read:chatters` | list of all viewers — only viewers who chat earn points for watching |
  | `moderation:read` | moderators list from Twitch — only badges in chat are seen |

  Twitch gives the list of all viewers and the moderators only with the channel owner's token: with a token of a separate bot account they do not work, even with every scope.
- **Token check on Connect.** The program asks Twitch whose token it is, which scopes it has and when it expires, and says in the tab's chat what is missing. An expired or revoked token stops the connect with a clear message. The **Client ID** can stay empty: it is taken from the token.
- **Save and connect** — you have to connect on every start of the program.
- **Automatic reconnect** after the connection drops.
- **Viewers / active chatters / moderators** — the lists in the right-hand panel. After you renew the token you may need to authenticate again.
- **Stream status** (LIVE / OFFLINE) — also needs a valid token.

> Queue control (`!queue`, `!skip`, `!clear`, `!volume`) is described separately — [queue.md](queue.md).

## Group Settings tab

Settings per command group (the column headers have tooltips):

| Column | What it does |
|---|---|
| **Queue** | A queue for the group: long sounds play one by one without cutting each other off |
| **Max size** | The queue limit (0 = no limit). When it is full, a command is rejected and its points refunded |
| **Channel** | The group's audio channel (0 = shared, 1–32 = its own channel, plays alongside the others) |
| **Persist** | Keep the group's queue across restarts |
| **Announce** | Tell the viewer their place in the queue (only if someone is already waiting) |

The groups are picked up from the commands automatically. After **Save Settings** the changes apply to the running bot without a restart; a playing track is not cut off.

## Queue Control tab

The running bot's queues live: what is playing and who is waiting. You can pause a group, skip the current sound, reorder (by dragging or with Up/Down), remove a command (Del) or empty the queue. More in [queue.md](queue.md).

## Sys.Commands tab

The system commands (`!points`, `!add_points`, `!remove_points`, `!random`, `!top`, `!give`, `!uptime`, `!queue`, `!skip`, `!clear`, `!volume`). You can turn them on and off, rename them (for example `!points` → `!balance`), change their permission, cooldowns and cost, make copies under another name, and pick the default group for `!volume`.

## Currency Settings tab

- The currency name, points for watching (online and offline) and their interval.
- Bonuses: **Regular** and **Mod** — extra points for the same interval, **Active** — for viewers who chatted (the *also offline* box — off stream too), **Sub multiplier ×** — how many times more subscribers get (×1 — the same as everyone).
- Rewards for a raid, a sub and a gift sub. The follow reward is not paid yet (it needs EventSub).
- Automatic **Regular** status by points or by hours.

## Currency Users tab

The viewers with their points and hours: add, change a balance, mark as Regular, remove.

## Ranks tab

Ranks by a threshold of points or hours (which one — *Rank type* on the currency tab). A rank is given automatically and shown in `!points`; changing the ranks recalculates them for every viewer at once.

## Backups tab

Command backups and full system backups (commands, settings, currency, ranks — without the Twitch token): create, view, restore. Automatic full backups are turned on in Settings → Auto-save & backups (in the classic theme — at the bottom of the commands tab).

## Settings tab

| Card | What it sets |
|---|---|
| **Sound** | Sounds interrupting each other and the message when a sound is blocked |
| **Auto-save & backups** | Auto-save of commands and viewers, automatic full backups |
| **Appearance** | The theme: Classic, Sidebar, Spreadsheet, Midnight (dark). Applies at once |
| **Language** | The interface language: System (default), Russian or English. Applies after a restart. Bot answers in chat and the values stored in files (`Everyone`, `SC`, group names) are not translated |
| **Permissions** | "Moderators have Admin rights" — see [Permissions](features.md#command-permissions) |
| **Global hotkeys** | See [Hotkeys](features.md#global-hotkeys) |
| **OBS overlay** | See [OBS overlay](features.md#obs-overlay) |

## Other

- A command can be edited in the table and in the panel under it (classic theme) or in the command card (the other themes) — the changes are saved at once.
- The fields edited most are `SoundFile` and `Cooldown` (in minutes).
- Both sound commands and text responses (`Response`) work; there is a built-in chat for checking.
- The program saves its settings safely even while the bot is connected.
