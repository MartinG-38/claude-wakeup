#!/usr/bin/env python3
"""
Claude Wakeup — Browser GUI
Opens in your default browser. No tkinter. Standard library only.
Auto-prevents sleep on macOS and Windows.
Detects battery vs AC power on macOS.
"""

import http.server
import json
import os
import platform
import socketserver
import subprocess
import threading
import time
import webbrowser
from datetime import datetime, timedelta

PORT = 18923

lock = threading.Lock()
state = {
    "screen": "main",
    "countdown": "",
    "response": "",
    "error_msg": "",
    "wake_time": "",
    "end_time": "",
}
cancel_event = threading.Event()
quit_event = threading.Event()


# ─── Power source detection ─────────────────────────────
def _normalize_cli_output(*parts):
    """Join CLI outputs safely for matching and display."""
    return "\n".join(part.strip() for part in parts if part and part.strip())


def detect_claude_error_message(stdout="", stderr="", returncode=None):
    """
    Convert Claude CLI failures into clearer user-facing messages.

    We use keyword matching because Claude CLI error phrasing can vary a bit
    across versions and account states.
    """
    combined = _normalize_cli_output(stdout, stderr)
    lowered = combined.lower()

    limit_markers = [
        "usage limit",
        "rate limit",
        "too many requests",
        "request limit",
        "maximum number of requests",
        "max requests",
        "limit reached",
        "quota exceeded",
        "try again later",
    ]
    auth_markers = [
        "not logged in",
        "login required",
        "authentication",
        "unauthorized",
        "forbidden",
    ]

    if any(marker in lowered for marker in limit_markers):
        return (
            "Claude reported that your request limit appears to be reached. "
            "Wait for your quota/window to reset, then try again."
        )

    if any(marker in lowered for marker in auth_markers):
        return (
            "Claude CLI appears to need authentication. "
            "Run 'claude' manually in this project and make sure you are logged in."
        )

    if combined:
        return (
            f"CLI error (exit code {returncode}). "
            f"Details: {combined}"
        )

    return f"CLI error (exit code {returncode})."


def check_power_source():
    """Check if Mac is on AC or battery. Returns 'ac', 'battery', or 'unknown'."""
    if platform.system() != "Darwin":
        return "unknown"
    try:
        result = subprocess.run(
            ["pmset", "-g", "ps"],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.lower()
        if "ac power" in output:
            return "ac"
        elif "battery" in output:
            return "battery"
    except Exception:
        pass
    return "unknown"


# ─── Prevent sleep (runs automatically) ─────────────────
def prevent_sleep():
    """
    macOS: launch caffeinate -i -s -w <pid>
      -i = prevent idle sleep (works on battery + AC)
      -s = prevent system sleep (only works on AC)
      -w = watch our PID, auto-exit when we exit
    Windows: SetThreadExecutionState
      ES_CONTINUOUS | ES_SYSTEM_REQUIRED = prevent sleep
    """
    system = platform.system()

    if system == "Darwin":
        power = check_power_source()
        flags = ["-i", "-s", "-w", str(os.getpid())]

        try:
            proc = subprocess.Popen(
                ["caffeinate"] + flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if power == "battery":
                print("WARNING: Running on battery!")
                print("  -i (idle sleep prevention) is active")
                print("  -s (system sleep prevention) only works on AC power")
                print("  -> Plug in your charger for best results")
                print("  -> Do NOT close the lid on battery")
            else:
                print("Sleep prevention: ON (caffeinate -i -s, on AC power)")
            return {"handle": proc, "power": power}
        except FileNotFoundError:
            print("Warning: caffeinate not found.")
            return None

    elif system == "Windows":
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            )
            print("Sleep prevention: ON (SetThreadExecutionState)")
            return {"handle": "windows", "power": "unknown"}
        except Exception:
            print("Warning: could not prevent sleep on Windows.")
            return None

    else:
        print(f"Warning: sleep prevention not implemented for {system}.")
        return None


def allow_sleep(info: "dict | None") -> None:
    """Release the sleep-prevention lock acquired by :func:`prevent_sleep`.

    Parameters
    ----------
    info : dict or None
        The value returned by :func:`prevent_sleep`. If ``None``, does nothing.
    """
    if info is None:
        return
    system = platform.system()

    if system == "Darwin" and info.get("handle") and info["handle"] != "windows":
        info["handle"].terminate()
        print("Sleep prevention: OFF")

    elif system == "Windows" and info.get("handle") == "windows":
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            print("Sleep prevention: OFF")
        except Exception:
            pass


# ─── HTML page ───────────────────────────────────────────
HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Claude Wakeup</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', sans-serif;
    background: #f5f5f7; color: #1d1d1f;
    display:flex; justify-content:center; align-items:center;
    min-height:100vh;
  }
  .card {
    background:white; border-radius:16px;
    box-shadow:0 4px 24px rgba(0,0,0,0.08);
    padding:40px; max-width:460px; width:100%;
    text-align:center;
  }
  h1 { font-size:28px; margin-bottom:6px; }
  .sub { color:#86868b; font-size:14px; margin-bottom:20px; }
  .box {
    background:#f5f5f7; border-radius:10px;
    padding:16px; text-align:left; margin-bottom:24px;
  }
  .box h3 { font-size:13px; margin-bottom:6px; }
  .box p { font-size:12px; color:#6e6e73; line-height:1.5; }
  .label { font-size:16px; font-weight:600; margin-bottom:10px; }
  .row {
    display:flex; justify-content:center;
    align-items:center; gap:8px; margin-bottom:8px;
  }
  select {
    font-size:22px; padding:8px 12px; border-radius:8px;
    border:1px solid #d2d2d7; background:white;
    text-align:center; width:85px;
  }
  .u { font-size:16px; color:#86868b; }
  .hint { font-size:11px; color:#aeaeb2; margin-bottom:20px; }
  .btn {
    display:inline-block; padding:12px 28px;
    border-radius:10px; border:none; cursor:pointer;
    font-size:15px; font-weight:600; margin:4px;
  }
  .p { background:#0071e3; color:white; }
  .p:hover { background:#0077ED; }
  .s { background:#e8e8ed; color:#1d1d1f; }
  .s:hover { background:#d2d2d7; }
  .q { background:#ff3b30; color:white; }
  .q:hover { background:#e0332b; }
  .cd { font-size:38px; font-weight:700; margin:16px 0; }
  .sm { font-size:14px; color:#86868b; margin-bottom:10px; }
  .st { font-size:28px; font-weight:700; color:#34c759; }
  .et { font-size:28px; font-weight:700; color:#ff3b30; }
  .rb {
    background:#f5f5f7; border-radius:10px;
    padding:14px; text-align:left; margin:14px 0;
    font-size:12px; line-height:1.6;
    max-height:150px; overflow-y:auto; word-wrap:break-word;
  }
  .ti { font-size:14px; font-weight:600; color:#34c759; margin:14px 0; }
  .sep { height:1px; background:#e8e8ed; margin:18px 0; }
  .hidden { display:none; }
  .bye { font-size:18px; color:#86868b; margin-top:40px; }
  .info { font-size:11px; margin-top:16px; min-height:16px; }
  .info-ok { color:#34c759; }
  .info-warn { color:#ff9500; font-weight:600; }
</style>
</head>
<body>
<div class="card">

  <div id="s-main">
    <h1>Claude Wakeup</h1>
    <p class="sub">Schedule your Claude CLI wake-up call</p>
    <div class="box">
      <h3>How it works:</h3>
      <p>Pick a wake-up time and press Start. The app waits in the
      background, then sends a prompt to Claude CLI at the scheduled
      time &mdash; starting your 5-hour token window.</p>
    </div>
    <div class="label">Wake-up time</div>
    <div class="row">
      <select id="hh"></select><span class="u">h</span>
      <select id="mm"></select><span class="u">min</span>
    </div>
    <p class="hint">Leave this page open overnight.</p>
    <button class="btn p" onclick="doStart()">Start Wakeup</button>
    <button class="btn q" onclick="doQuit()">Quit</button>
    <p class="info" id="power-main"></p>
  </div>

  <div id="s-wait" class="hidden">
    <h1>ALARM SET</h1>
    <div class="sep"></div>
    <p class="sm" id="wmsg"></p>
    <p class="sm">Waiting...</p>
    <div class="cd" id="cd">--h --m --s</div>
    <button class="btn s" onclick="doCancel()">Cancel</button>
    <button class="btn q" onclick="doQuit()">Quit</button>
    <p class="info" id="power-wait"></p>
  </div>

  <div id="s-wake" class="hidden">
    <h1>Waking up Claude...</h1>
    <div class="sep"></div>
    <p class="sm">Sending prompt to Claude CLI...</p>
    <p class="sm">This may take a moment.</p>
    <br>
    <button class="btn q" onclick="doQuit()">Quit</button>
  </div>

  <div id="s-ok" class="hidden">
    <div class="st">SUCCESS</div>
    <p style="font-size:16px;font-weight:600;margin:6px 0 14px">Claude is awake!</p>
    <p style="font-size:12px;font-weight:600;text-align:left">Claude's response:</p>
    <div class="rb" id="resp"></div>
    <div class="ti" id="tinfo"></div>
    <button class="btn p" onclick="doReset()">Schedule another</button>
    <button class="btn q" onclick="doQuit()">Quit</button>
  </div>

  <div id="s-err" class="hidden">
    <div class="et">ERROR</div>
    <div class="sep"></div>
    <p class="sm" id="emsg"></p><br>
    <button class="btn p" onclick="doReset()">Try again</button>
    <button class="btn q" onclick="doQuit()">Quit</button>
  </div>

  <div id="s-bye" class="hidden">
    <h1>Goodbye!</h1>
    <p class="bye">Server stopped. You can close this tab.</p>
  </div>

</div>
<script>
var hh=document.getElementById('hh'),mm=document.getElementById('mm');
for(var h=0;h<24;h++){
  var o=document.createElement('option');
  o.value=o.textContent=String(h).padStart(2,'0');
  if(h==6)o.selected=true;
  hh.appendChild(o);
}
for(var m=0;m<60;m+=5){
  var o=document.createElement('option');
  o.value=o.textContent=String(m).padStart(2,'0');
  mm.appendChild(o);
}

var ids=['main','wait','wake','ok','err','bye'];
function show(n){
  ids.forEach(function(s){
    document.getElementById('s-'+s).className=(s===n?'':'hidden');
  });
}

var poll=null;

function doStart(){
  var h=hh.value,m=mm.value;
  fetch('/start',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({hour:parseInt(h),minute:parseInt(m)})
  });
  document.getElementById('wmsg').textContent=
    'Claude will be woken up at '+h+':'+m;
  show('wait');
  poll=setInterval(pollStatus,1000);
}

function doCancel(){
  fetch('/cancel',{method:'POST'});
  if(poll)clearInterval(poll);
  show('main');
}

function doReset(){
  if(poll)clearInterval(poll);
  show('main');
}

function doQuit(){
  if(poll)clearInterval(poll);
  fetch('/quit',{method:'POST'}).catch(function(){});
  show('bye');
}

function pollStatus(){
  fetch('/status').then(function(r){return r.json();}).then(function(d){
    if(d.screen==='waiting'){
      document.getElementById('cd').textContent=d.countdown;
    }else if(d.screen==='waking'){
      show('wake');
    }else if(d.screen==='success'){
      clearInterval(poll);
      document.getElementById('resp').textContent=d.response;
      document.getElementById('tinfo').textContent=
        'Woke up at '+d.wake_time+' \\u2014 End of 5h window at '+d.end_time;
      show('ok');
    }else if(d.screen==='error'){
      clearInterval(poll);
      document.getElementById('emsg').textContent=d.error_msg;
      show('err');
    }
  }).catch(function(){});
}

function checkPower(){
  fetch('/power').then(function(r){return r.json();}).then(function(d){
    var msg='', cls='info-ok';
    if(d.power==='ac'){
      msg='On AC power — sleep prevention active. You can lock your screen.';
    }else if(d.power==='battery'){
      msg='WARNING: On battery! Plug in your charger for best results. Do NOT close the lid.';
      cls='info-warn';
    }else{
      msg='Sleep prevention active. You can lock your screen.';
    }
    var e1=document.getElementById('power-main');
    if(e1){e1.textContent=msg;e1.className='info '+cls;}
    var e2=document.getElementById('power-wait');
    if(e2){e2.textContent=msg;e2.className='info '+cls;}
  }).catch(function(){});
}
checkPower();
setInterval(checkPower,30000);
</script>
</body>
</html>"""


# ─── HTTP handler ────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        """Silence the default per-request log output."""

    def do_GET(self) -> None:
        """Handle GET requests: serve the HTML page, status JSON, or power JSON."""
        if self.path == "/":
            self._send(200, "text/html", HTML_PAGE.encode())
        elif self.path == "/status":
            with lock:
                data = json.dumps(state)
            self._send(200, "application/json", data.encode())
        elif self.path == "/power":
            power = check_power_source()
            self._send(200, "application/json",
                       json.dumps({"power": power}).encode())
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self) -> None:
        """Handle POST requests: /start, /cancel, /quit."""
        if self.path == "/start":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n)) if n else {}
            h, m = body.get("hour", 6), body.get("minute", 0)

            now = datetime.now()
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)

            cancel_event.clear()
            with lock:
                state["screen"] = "waiting"
                state["countdown"] = ""

            threading.Thread(target=worker, args=(target,), daemon=True).start()
            self._send(200, "text/plain", b"ok")

        elif self.path == "/cancel":
            cancel_event.set()
            with lock:
                state["screen"] = "main"
            self._send(200, "text/plain", b"ok")

        elif self.path == "/quit":
            cancel_event.set()
            quit_event.set()
            self._send(200, "text/plain", b"ok")

        else:
            self._send(404, "text/plain", b"Not found")

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        """Send an HTTP response with the given status code, content type, and body."""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ─── Background worker ──────────────────────────────────
def worker(target: datetime) -> None:
    """Background thread: count down to *target*, then invoke Claude CLI.

    Updates the global ``state`` dict each second and sets the screen to
    ``"waking"``, ``"success"``, or ``"error"`` when the time comes.
    Exits early if ``cancel_event`` is set.

    Parameters
    ----------
    target : datetime
        Local datetime at which the wake-up prompt should be sent.
    """
    while datetime.now() < target:
        if cancel_event.is_set():
            return
        rem = (target - datetime.now()).total_seconds()
        rh = int(rem // 3600)
        rm = int(rem % 3600 // 60)
        rs = int(rem % 60)
        with lock:
            state["countdown"] = f"{rh:02d}h {rm:02d}m {rs:02d}s"
        time.sleep(1)

    if cancel_event.is_set():
        return

    with lock:
        state["screen"] = "waking"

    try:
        result = subprocess.run(
            ["claude", "-p", "Good morning Claude, time to wake up!"],
            timeout=120, check=True,
            capture_output=True, text=True,
        )
        resp = (result.stdout or "(no response)").strip()
        now_str = datetime.now().strftime("%H:%M")
        end_str = (datetime.now() + timedelta(hours=5)).strftime("%H:%M")
        with lock:
            state["screen"] = "success"
            state["response"] = resp
            state["wake_time"] = now_str
            state["end_time"] = end_str
    except FileNotFoundError:
        with lock:
            state["screen"] = "error"
            state["error_msg"] = (
                "'claude' not found in PATH. "
                "Make sure the Claude CLI is installed."
            )
    except subprocess.TimeoutExpired:
        with lock:
            state["screen"] = "error"
            state["error_msg"] = (
                "Timeout: Claude did not respond within 2 minutes."
            )
    except subprocess.CalledProcessError as e:
        cli_output = _normalize_cli_output(e.stdout, e.stderr)
        with lock:
            state["screen"] = "error"
            state["error_msg"] = detect_claude_error_message(
                stdout=e.stdout,
                stderr=e.stderr,
                returncode=e.returncode,
            )
            state["response"] = cli_output


# ─── Server ──────────────────────────────────────────────
class Server(socketserver.TCPServer):
    allow_reuse_address = True


def main() -> None:
    """Start the local HTTP server, open the browser, and wait for quit."""
    # Start sleep prevention
    sleep_handle = prevent_sleep()

    srv = Server(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    url = f"http://127.0.0.1:{PORT}"
    print(f"Claude Wakeup running at {url}")
    print("Sleep prevention: active (screen lock OK, system won't sleep)")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)

    try:
        while not quit_event.is_set():
            time.sleep(0.5)
        print("\nQuit from browser. Stopping...")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        allow_sleep(sleep_handle)
        srv.shutdown()


if __name__ == "__main__":
    main()
