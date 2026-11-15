# Queues

🇷🇺 [Русская версия](ru/queue.md)

Commands with a queue turned on run **one after another within their group**: the next sound starts only after the previous one ends. This is for music and other long sounds that would otherwise cut each other off.

Groups without a queue work as before: a sound plays at once, and a new one may cut off the old one (depending on the *Allow sounds to interrupt* setting).

## How it works

- Every group with a queue gets its own queue and its own worker: it takes the commands one at a time and waits for the sound to end.
- Different groups play **at the same time**, each on its own audio channel.
- The queue limit counts what is really there: the waiting commands plus the current one. When the queue is full, a command is rejected and the points taken for it are refunded.
- Saving a group's settings applies to the running bot at once and **does not cut off** the playing track.
- If you turn a group's queue off, the commands already paid for still play, and new ones run at once.

## Setting up a group

**Group Settings** tab (the column headers have tooltips):

1. **Queue**: turn on the queue for the group.
2. **Channel**: the playback channel.
   - `shared` (0): the shared channel, sounds may cut each other off.
   - `1–32`: its own channel, plays alongside and does not cut off the shared one. Do not give two queued groups the same channel; the program warns you about it.
3. **Max size**: how many commands may wait in the queue, the current one included (`unlimited` = no limit).
4. **Persist**: keep the queue across restarts (see below).
5. **Announce**: tell the viewer their place in the queue (only if someone is already ahead of them).

Press **Save Settings**.

## Queue Control tab

- The **Now playing** block: what is playing now, who ordered it, how long it has been playing.
- **Pause / Resume**: the current command finishes, new ones do not start, the order stays.
- **Skip**: skip what is playing now (the sound and the text response).
- The **Up next** list: drag and drop, **Up/Down** buttons, **Remove** (or the Del key), **Clear all** (asks first). Exactly the selected entry is removed, even if the queue holds several copies of the same command; the current track is not interrupted.
- In the **Midnight** theme a Now playing bar with Pause/Skip for every queue is always visible at the bottom of the window.

## Commands

| Command | Who | What it does |
|---|---|---|
| `!queue` | everyone | a summary of all active queues (`Group: N`) |
| `!queue GROUP` | everyone | what is playing now and what comes next (up to 15) in one line |
| `!skip` | mod | skip the current item of the only queue that is playing; otherwise stop the shared channel |
| `!skip GROUP` | mod | skip what the group is playing now |
| `!skip COMMAND` | mod | remove the last waiting entry of this command (the current track is not touched) |
| `!clear GROUP` | mod | remove the group's waiting commands |
| `!volume <0-100>` | mod | the volume of the default group (set in Sys.Commands, `SONG` by default) |
| `!volume GROUP <0-100>` | mod | a group's volume; applies to the current track at once and is saved. `0` = muted |

> Group names in commands are not case-sensitive.

## Order and cost

- A command joins the queue **after** the cooldown checks and after its points are taken. The cooldown starts only when the command is accepted into the queue.
- If the queue is full, the command is not accepted, its points are refunded and a message is sent.
- The worker runs a command: the cost (if not taken yet), the sound (to the end), then the text response.

## Keeping the queue (Persist Queue)

By default the queue is **not** kept: when the program restarts, the waiting commands are lost. This is on purpose: not everyone wants music to "finish playing" after a restart.

To keep a group's queue:

1. In **Group Settings** turn on **Persist Queue** for that group.
2. Every change of the queue is written to `config.json` (the `queue_persistence` section), including the track playing now: it is not lost after a crash.
3. The next time the bot starts, the group's queue is restored and keeps playing.

Details:

- Restored commands run from the saved data (sound + response). They have no live Twitch message, so their chat responses are not sent to chat on restore — only the sound and the log.
- `!clear GROUP` also resets the saved queue, so cleared entries do not "come back to life" after a restart.
- Only groups with **Persist Queue** turned on are kept; other groups are not touched.

## Example: music

1. Create a `SONG` group, give it channel `1`, turn on the queue and (optionally) Persist Queue.
2. Move all music commands to the `SONG` group.
3. Viewers queue music: `!song ...` — tracks play one by one without cutting each other off.
4. A mod manages it: `!queue SONG` (what is playing / waiting), `!skip SONG` (skip), `!volume SONG 50` (volume), `!clear SONG` (empty the queue).
