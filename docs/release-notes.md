# Release notes

🇷🇺 [Русская версия](ru/release-notes.md)

## 2.0 (beta: V2.0.0-Beta1)

The highlights: a Russian and English interface, timers, statistics, an OBS
overlay, global hotkeys, variables and aliases in commands, new permission
levels, a trash and testing a command without Twitch. Plus dozens of fixes:
raid and sub rewards, the bot's reconnect, command permissions, ranks,
currency bonuses.

### Important: how points are paid has changed
- **The Regular bonus is paid only on the timer.** A regular used to get the
  bonus twice: in proportion to the watch-time payouts and once more on any
  payout (a refund for a sound that did not play, a transfer from another
  viewer, a manual grant). Only the first one is left, so regulars' balances
  grow more slowly than in 1.x.
- **No payouts for downtime.** If more than 10 minutes passed between two
  updates of the viewer list (the bot was disconnected, the computer was
  asleep), that time earns no points or hours. The first update after a break
  used to pay for the whole time offline.

### New
- **Russian and English interface.** The system language by default (Russian
  Windows — Russian, otherwise English); change it in Settings → Language,
  after a restart. The bot's answers in chat and the values in command files
  (Everyone, SC, SONG…) are not translated.
- **Statistics** (Stats tab): popular commands, the points economy (earned,
  rewards, spent, given), top viewers by points and hours — for today, 7, 30
  or 90 days.
- **A random sound from a folder:** a command can have a folder instead of a
  file (Folder…) — each call plays a random sound from it, never the same one
  twice in a row.
- **Command trash:** a deleted command is not lost — Ctrl+Z puts the last one
  back in its place, Trash… shows up to 50 deleted ones.
- **Test a command without Twitch** (the Test… button): does the message call
  the command, is a viewer of that role allowed, do they have enough points,
  which answer goes to chat and is there a sound. Nothing is taken or counted.
- **Timers** (Timers tab): bot messages in chat every N minutes, only if the
  chat had at least M messages, optionally only while live.
- **OBS overlay** (Settings → OBS overlay): a page for a Browser Source —
  what is playing, the queues, the latest commands with the viewers; a
  transparent background, the blocks and the font size are chosen in the
  address. Opens only on this computer (127.0.0.1).
- **Global hotkeys** (Settings → Global hotkeys): skip the sound, pause the
  queues and "stop everything" — they work with the window minimised and in a
  game. Off by default; combinations taken by another program are shown on
  the card.
- **Variables in command responses:** `{target}`, `{args}`, `{1}`…`{9}`,
  `{count}`, `{points}`, `{currency}`, `{channel}`, `{random:1-100}` (only
  `{user}` before). The list is in docs/features.md.
- **Command aliases:** the Aliases field (`!music, !tune`) — other names of
  the same command with its cooldown, cost and counter.
- **New command permissions: Regular, Subscriber, VIP.** The ladder Everyone →
  Regular → Subscriber → VIP → Moderator → Admin; each level includes the
  lower ones. Subs and VIPs are recognised by their chat badges, regulars by
  their currency status.
- **Admin can be separated from Moderator.** By default, as in 1.x, a
  moderator may call Admin commands. Settings → Permissions → "Moderators
  have Admin rights" turns that off: then Admin is only the channel owner and
  the names in the `admins` list of `moderators.json` (the "Open moderators
  file" button on the Twitch tab); they are shown in the moderators list as
  [Admin].
- **Starting the program a second time with the same data folder does not
  open a second window**, it warns that the program is already running: two
  copies overwrote each other's saves. Copies with different data folders
  work as before.
- The Active Bonus on the currency tab got an "also offline" box.
- **Token check on Connect:** whose token it is, which scopes are missing and
  what will not work without them, how long it still lives; a token that is
  not the streamer's — a warning that the viewer and moderator lists will be
  incomplete. An expired token stops the connect with a clear message
  instead of "reconnect manually". The Client ID is no longer required — it
  is taken from the token.

### Changed
- **Sub Bonus is called what it always was — a multiplier** ("Sub multiplier
  ×"): ×1 — the same as everyone, ×3 — three times more. A value of 0 left
  subscribers with no points for watching; the minimum is now ×1, and a saved
  0 is corrected to ×1 on start. The "Max …/h" hint counts the multiplier
  correctly (it used to add it as points and understate the maximum).
- A new installation starts without bonuses: Regular 0, Mod 0, Active 0,
  Sub ×1. Without a settings file it used to set Regular 1 and Mod 2. Saved
  settings do not change.
- **The Active Bonus is paid.** The field was there before, but the bonus was
  never paid. Now a viewer who chatted since the last payout gets it, in
  proportion to the time like the Regular and Mod bonuses (offline — only
  with `offline_active_bonus`). 0 by default; a saved 1 (the old default) is
  reset to 0 on the first start so balances do not start growing unasked —
  set your own value if you want it.
- The Active Chatters tab shows who wrote in chat in the last 10 minutes
  (before — every viewer at the moment of connecting).
- Currency tab: removed the "Command" field (it did nothing — the balance
  command `!points` is renamed in Sys.Commands, like the other system
  commands) and the "On Host" reward (Twitch removed hosts in 2022).
- Deleting a command asks first (it used to delete at once).

### Fixed
- The bot no longer goes deaf after losing the connection to Twitch: it
  reconnects automatically (also after Twitch itself closes the connection or
  asks to reconnect); the program's chat shows "connection lost" /
  "restored".
- **Raid and sub rewards work** (they were never paid before): a raid, a sub
  or resub (Tier 2 ×2, Tier 3 ×5), a gift sub — to the recipient and the
  gifter. Follow rewards are not paid yet: Twitch does not report follows
  through chat; they will come separately (EventSub).
- The Sys.Commands settings of `!queue`, `!skip`, `!clear`, `!volume` take
  effect (on/off, permission, cooldown, cost), and copies of these commands
  work. The cooldowns, which never took effect before, are reset to 0 on the
  first start — nothing changes for viewers, you can set your own later.
- `!random` works like an ordinary call of the chosen command: it goes
  through its group's queue and channel, uses the group's volume, refunds the
  points if the sound did not play, and counts the use.
- Two quick identical commands no longer both slip past the cooldown.
- "Allow sounds to interrupt each other" works on every audio channel: on the
  channel of a group without a queue a new sound always cut off the old one.
- A sound file replaced on disk is picked up without a restart.
- Command permissions work: an ordinary viewer cannot call a Moderator/Admin
  command (the level of ordinary commands was not checked before).
- A moderator with a badge in chat is recognised at once, without asking
  Twitch; Everyone commands do not check for a moderator at all — the bot no
  longer stalls on every system command.
- Classic theme: the fields of the **Command Details** panel (name,
  permission, description, group, cooldowns, cost, counter, Usage, Enabled,
  sound files, the Browse buttons) keep their changes — everything except the
  response and the volume used to be lost. Cooldown and cost are no longer
  capped at 99. A new command is saved at once.
- **Load File** loads the file again: the import used to be overwritten by
  the old commands right away.
- Edits after loading a file or restoring a backup go to the right command.
- Commands with the same name are no longer lost when the program exits.
- A new token from the authentication window applies at once, without a
  restart.
- Giving points (`!give`) is more reliable; you cannot give to yourself or to
  a name that does not exist.
- A full restore from a backup writes the restored currency and recalculates
  the viewers' ranks for the restored thresholds.
- **A full backup no longer contains the Twitch token.** The backup file
  (`backups/comprehensive/system_backup_*.json`) used to get all of
  `twitch_config.json`, access token included, although a restore used only
  the channel. Delete old backups with the token if you share them with
  anyone.
- Two full backups in the same second no longer overwrite each other.
- The Play Sound button is no longer changed from a background thread.
- Picking a sound file with the button in the themes (Sidebar, Midnight,
  Spreadsheet) no longer also writes it to FK Sound File (of the same
  command, and in Spreadsheet sometimes of another one).
- Commands from Streamlabs exports with Regular / Subscriber permissions used
  to be open to everyone — now these permissions work.
- The automatic Regular status "by hours" works: choosing Hours on the
  currency tab used to be ignored and the status was always given by points.
- Currency viewers tab: "Add User" with capital letters in the name no longer
  crashes; Edit → Save no longer cuts the balance to 999,999 or drops the
  fraction; the moderator status set on the Twitch tab is saved to the file.
- A group on audio channel 32 (Group Settings offers it) now plays: that
  channel did not exist and the group's sounds did not play.
- Play Sound in the editor plays on its own channel and no longer cuts off a
  viewer's sound on stream (nor is it blocked by one).
- Fixed a possible complete freeze of the program: a viewer's rank promotion
  or a command payment while the currency was being saved from another thread
  could lock up both the window and the bot for good.
- The update check compares versions correctly: it could not parse its own
  `V1.1.6a` and offered to "update" to any other tag, older ones included.
  The version in About is `V2.0.0-Beta1`.
- Currency viewers tab: the table no longer stops refreshing while the bot
  pays points, the Edit/Remove buttons are not recreated every 30 seconds,
  and an empty list clears the table.
- Auto-save no longer floods the history (History tab) with identical copies:
  a backup is made only if the commands changed. A copy used to appear every
  5 minutes, and within a few hours the real old versions dropped out of the
  history.
- Checking someone else's balance or a moderator command with a typo in the
  name no longer adds an empty viewer to `users_currency.json`.
- `!volume` for a group without a queue applies to the next sound.
- Ranks work: they are given by thresholds, shown in `!points`, and changing
  the ranks on the tab recalculates them for everyone at once.
- Raid/follow/sub rewards from the currency tab are saved under the keys the
  bot reads (old settings are moved over automatically).
- The first start in an empty folder creates `config.json`; a corrupted
  `config.json` is not silently overwritten but kept next to it as
  `config.json.corrupt-<time>`.
- Random crashes when updating the viewer list (widgets were changed from the
  bot's thread) and a stream status error every 30 seconds.
- The window and the bot talk only through one bridge: no button, setting or
  command edit touches the bot from the interface thread. The stream status
  is asked from Twitch once every 30 seconds, not twice. The "Bot
  disconnected, reconnect manually" message appears only when the bot stopped
  by itself, not after the Disconnect button.

### Reliability
- All data files (`commands.json`, the settings, currency, ranks, backups)
  are written atomically: a power cut or a crash in the middle of a save
  leaves the previous whole file.
- A crash log `command_editor_crash.log` next to the program; an exception in
  the interface no longer closes the program. The previous run's log is kept
  as `command_editor.log.1` (up to three previous ones).
