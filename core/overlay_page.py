"""The OBS overlay page (served by core/overlay.py). Plain HTML + JS, no
external files: OBS Browser Source loads it from 127.0.0.1.

URL options:  ?show=now,queue,recent   which blocks (default: all three)
              ?size=24                 font size in px
"""

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Command Editor overlay</title>
<style>
  html, body { background: transparent; margin: 0; padding: 8px; }
  body { font-family: "Segoe UI", Arial, sans-serif; color: #fff;
         text-shadow: 0 0 3px #000, 0 0 6px #000; font-size: var(--size, 22px); }
  .block { margin-bottom: 0.6em; }
  .title { font-size: 0.7em; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.8; }
  .row { line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cmd { font-weight: 700; }
  .user { opacity: 0.85; }
  .muted { opacity: 0.6; font-size: 0.8em; }
  .hidden { display: none; }
</style></head>
<body>
<div id="now" class="block"></div>
<div id="queue" class="block"></div>
<div id="recent" class="block"></div>
<script>
var params = new URLSearchParams(location.search);
var show = (params.get("show") || "now,queue,recent").split(",");
if (params.get("size")) document.body.style.setProperty("--size", params.get("size") + "px");
["now", "queue", "recent"].forEach(function (b) {
  if (show.indexOf(b) < 0) document.getElementById(b).className = "block hidden";
});
function esc(s) { return String(s).replace(/[&<>"]/g, function (c) {
  return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
function mmss(s) { s = Math.max(0, s | 0); return Math.floor(s / 60) + ":" + ("0" + s % 60).slice(-2); }
function render(st) {
  var now = st.now.map(function (n) {
    return '<div class="row">&#9654; <span class="cmd">' + esc(n.command) + '</span> <span class="user">' +
           esc(n.user) + '</span> <span class="muted">' + mmss(n.elapsed) + '</span></div>'; });
  document.getElementById("now").innerHTML = now.length ? '<div class="title">Now playing</div>' + now.join("") : "";
  var q = [];
  st.queues.forEach(function (g) {
    if (!g.pending.length) return;
    q.push('<div class="title">' + esc(g.group) + (g.paused ? " (paused)" : "") + '</div>');
    g.pending.forEach(function (p, i) {
      q.push('<div class="row">' + (i + 1) + '. <span class="cmd">' + esc(p.command) +
             '</span> <span class="user">' + esc(p.user) + '</span></div>'); });
    if (g.more) q.push('<div class="row muted">+' + g.more + ' more</div>');
  });
  document.getElementById("queue").innerHTML = q.join("");
  var r = st.recent.slice().reverse().map(function (c) {
    return '<div class="row"><span class="cmd">' + esc(c.command) + '</span> <span class="user">' +
           esc(c.user) + '</span></div>'; });
  document.getElementById("recent").innerHTML = r.length ? '<div class="title">Recent</div>' + r.join("") : "";
}
function poll() {
  fetch("state.json", {cache: "no-store"}).then(function (r) { return r.json(); })
    .then(render).catch(function () {}).then(function () { setTimeout(poll, 1000); });
}
poll();
</script>
</body></html>
"""
