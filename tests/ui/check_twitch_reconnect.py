"""C2 with the real twitchio: a local WebSocket server speaks just enough of
Twitch IRC; the connection is dropped and Twitch's RECONNECT is sent. The
bot must come back by itself and keep answering commands.

Run by tests/ui/run_ui.py (needs the real twitchio/aiohttp/pygame, no Qt).
"""
import asyncio
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, _OUT = uikit.args()
fixture.write_json(DATA, "commands.json", [fixture.command("!hi", Response="hello")])
fixture.write_json(DATA, "config.json", fixture.base_config(twitch={"channel": "testchan"}))
fixture.write_json(DATA, "twitch_config.json",
                   {"access_token": "faketoken", "client_id": "cid", "refresh_token": ""})
os.environ["COMMAND_EDITOR_HOME"] = DATA
os.chdir(DATA)
sys.path.insert(0, uikit.REPO)
uikit._disable_network()

import pygame  # noqa: E402
pygame.mixer.init()
from aiohttp import web, WSMsgType  # noqa: E402
import twitchio.websocket  # noqa: E402
import twitchio.http  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append(("PASS" if cond else "FAIL", name, detail))


class FakeTwitch(object):
    """Minimal Twitch IRC over WebSocket."""

    def __init__(self):
        self.connections = 0
        self.sockets = []
        self.from_bot = []
        self.msg_id = 0
        self.down_until = 0.0

    async def handler(self, request):
        if time.monotonic() < self.down_until:  # simulated outage
            return web.Response(status=503)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.connections += 1
        self.sockets.append(ws)
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            for line in msg.data.split("\r\n"):
                if not line:
                    continue
                self.from_bot.append(line)
                if line.startswith("NICK"):
                    await ws.send_str(":tmi.twitch.tv 001 botnick :Welcome, GLHF!\r\n"
                                      ":tmi.twitch.tv 376 botnick :>\r\n")
                elif line.startswith("JOIN"):
                    chan = line.split()[1]
                    await ws.send_str(
                        ":botnick!botnick@botnick.tmi.twitch.tv JOIN %s\r\n"
                        ":botnick.tmi.twitch.tv 353 botnick = %s :botnick\r\n"
                        ":botnick.tmi.twitch.tv 366 botnick %s :End of /NAMES list\r\n"
                        % (chan, chan, chan))
        return ws

    async def say(self, user, text):
        ws = self.sockets[-1]
        self.msg_id += 1
        # the tags real Twitch always sends (twitchio needs e.g. color)
        tags = ("@badge-info=;badges=;color=#1E90FF;display-name=%s;emotes=;first-msg=0;"
                "flags=;id=00000000-0000-0000-0000-%012d;mod=0;returning-chatter=0;room-id=1;"
                "subscriber=0;tmi-sent-ts=%d;turbo=0;user-id=%d;user-type="
                % (user, self.msg_id, int(time.time() * 1000), 100 + self.msg_id))
        await ws.send_str("%s :%s!%s@%s.tmi.twitch.tv PRIVMSG #testchan :%s\r\n"
                          % (tags, user, user, user, text))

    def replies(self):
        return [l for l in self.from_bot if l.startswith("PRIVMSG #testchan")]


async def wait_for(cond, timeout=10.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        await asyncio.sleep(0.05)
    return False


async def main():
    fake = FakeTwitch()
    app = web.Application()
    app.router.add_get("/", fake.handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    twitchio.websocket.HOST = "ws://127.0.0.1:%d/" % port

    async def fake_validate(self, *, token=None):
        import aiohttp
        if not self.session:  # the real validate() creates the session too
            self.session = aiohttp.ClientSession()
        return {"login": "botnick", "user_id": "1", "client_id": "cid", "scopes": []}
    twitchio.http.TwitchHTTP.validate = fake_validate

    from config_manager import ConfigManager
    from twitch_bot import TwitchBot
    said = []
    bot = TwitchBot(channel="testchan", config_manager=ConfigManager(),
                    message_callback=said.append)
    bot._watch_interval = 0.2
    bot.update_commands([fixture.command("!hi", Response="hello")])  # as TwitchTab.run_bot does

    async def no_helix(*a, **k):
        return []
    bot.get_all_viewers = no_helix
    bot.get_channel_moderators = no_helix

    async def offline(*a, **k):
        return False
    bot.check_if_live = offline
    bot._stream_status_loop = lambda: asyncio.sleep(0)

    start = asyncio.ensure_future(bot.start())
    try:
        ok = await wait_for(lambda: bot.initialized_event.is_set() and fake.connections == 1)
        check("connects and becomes ready", ok, (fake.connections, fake.from_bot[-5:],
              start.done() and (start.exception() if not start.cancelled() else "cancelled")))

        await fake.say("viewer", "!hi")
        ok = await wait_for(lambda: any("hello" in r for r in fake.replies()))
        check("answers a command", ok, fake.replies())

        # S7: a raid arrives as USERNOTICE (format of real Twitch messages)
        n = len(fake.replies())
        await fake.sockets[-1].send_str(
            "@badge-info=;badges=;color=#FF0000;display-name=Raider;emotes=;flags=;"
            "id=11111111-2222-3333-4444-555555555555;login=raider;mod=0;msg-id=raid;"
            "msg-param-displayName=Raider;msg-param-login=raider;msg-param-profileImageURL=x;"
            "msg-param-viewerCount=42;room-id=1;subscriber=0;"
            "system-msg=42\\sraiders\\sfrom\\sRaider\\shave\\sjoined!;tmi-sent-ts=1700000000000;"
            "user-id=2;user-type= :tmi.twitch.tv USERNOTICE #testchan\r\n")
        cur = bot.currency_manager
        ok = await wait_for(lambda: cur.users.get("raider", {}).get("points", 0) > 0)
        expected = cur.settings.get("raid_points", 10) + 42 * cur.settings.get("raid_points_per_viewer", 1)
        check("raid USERNOTICE pays the raider (S7)",
              ok and abs(cur.users["raider"]["points"] - expected) < 0.01,
              (cur.users.get("raider"), expected))
        ok = await wait_for(lambda: len(fake.replies()) > n)
        check("raid thank-you sent to chat", ok and "Raider" in fake.replies()[-1], fake.replies()[-1:])

        # 1. the connection drops and Twitch is unreachable for a moment
        fake.down_until = time.monotonic() + 1.5
        await fake.sockets[-1].close()
        ok = await wait_for(lambda: fake.connections == 2 and bot._connection_alive(), 15)
        keeper = getattr(bot._connection, "_keeper", None)
        keeper_state = None
        if keeper is not None and keeper.done() and not keeper.cancelled():
            keeper_state = repr(keeper.exception())
        check("reconnects by itself after a dropped connection", ok,
              "connections=%d, twitchio keep-alive task: %s" % (fake.connections, keeper_state))
        check("bot never stopped handling chat", bot.initialized_event.is_set())
        n = len(fake.replies())
        await asyncio.sleep(0.3)
        await fake.say("viewer2", "!hi")
        ok = await wait_for(lambda: len(fake.replies()) > n)
        check("answers after the reconnect", ok, fake.replies())
        await asyncio.sleep(0.5)
        check("UI told: lost and restored",
              any("lost" in s.lower() for s in said) and any("restored" in s.lower() for s in said),
              [s for s in said if "onnect" in s])

        # 2. Twitch asks to reconnect (server maintenance)
        await fake.sockets[-1].send_str(":tmi.twitch.tv RECONNECT\r\n")
        ok = await wait_for(lambda: fake.connections == 3 and bot._connection_alive(), 15)
        check("follows Twitch's RECONNECT", ok, fake.connections)
        n = len(fake.replies())
        await asyncio.sleep(0.3)
        await fake.say("viewer3", "!hi")
        ok = await wait_for(lambda: len(fake.replies()) > n)
        check("answers after RECONNECT", ok, fake.replies())
    finally:
        bot.is_running = False
        try:
            await asyncio.wait_for(bot.close(), 5)
        except Exception:
            pass
        start.cancel()
        try:
            await start
        except BaseException:
            pass
        await runner.cleanup()


try:
    asyncio.get_event_loop().run_until_complete(asyncio.wait_for(main(), 90))
except Exception:
    results.append(("FAIL", "exception", traceback.format_exc()))
out = sys.__stdout__
for status, name, detail in results:
    line = "%s  %s" % (status, name)
    if status == "FAIL" and detail != "":
        line += "  " + str(detail).replace("\n", "\n      ")
    out.write(line + "\n")
out.flush()
