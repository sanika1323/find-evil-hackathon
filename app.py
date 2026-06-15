"""Find Evil! - Autonomous DFIR Triage Agent (live integration + showcase UI).

Integration is unchanged in substance: collect.sh gathers evidence read-only, then
`claude -p` analyzes the bundle per CLAUDE.md (same binary, same args, same log file).
The agent run is now *streamed* so the UI can show the agent's reasoning and tool
calls in real time - everything else about the integration is identical.

Showcase additions (presentation only):
  * Real-time "agent stream" terminal during analysis
  * Animated command-center hero
  * Force-directed IOC graph + event timeline
  * Config-file login / logout, no sidebar, focused tabs

Run:  streamlit run app.py
Optional libs (graceful fallback):  pip3 install --break-system-packages plotly streamlit-option-menu
"""
from __future__ import annotations
import os, re, io, glob, json, time, math, html, shutil, tempfile, hashlib, subprocess
from collections import Counter
from datetime import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_option_menu import option_menu
    HAS_MENU = True
except Exception:
    HAS_MENU = False
try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except Exception:
    HAS_PLOTLY = False

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


def _rerun():
    fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if fn:
        fn()


def _esc(s):
    return html.escape(str(s) if s is not None else "")


st.set_page_config(page_title="Find Evil! - DFIR Triage", page_icon="🛡️",
                   layout="wide", initial_sidebar_state="expanded")

# ============================================================================
#  GLOBAL THEME
# ============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root{
  --bg:#070b16;--panel:#0d1626;--panel2:#101c33;--line:#1b2942;
  --accent:#3b82f6;--accent2:#38d6ff;--ink:#e8eefb;--muted:#93a4c4;
  --crit:#ff4b5c;--high:#ff9f1c;--med:#ffd23f;--low:#4dabf7;--good:#22c55e;
}
html,body,[class*="css"]{font-family:'Inter',system-ui,sans-serif!important;}
[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(1200px 620px at 8% -12%,#13316b3d,transparent 55%),
    radial-gradient(1100px 560px at 100% -4%,#0e3a5a38,transparent 50%),
    radial-gradient(900px 760px at 50% 124%,#10224a2e,transparent 60%),
    var(--bg);
}
[data-testid="stHeader"]{background:transparent;}
.block-container{padding-top:1.0rem;padding-bottom:3rem;max-width:1320px;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0b1626,#070d18);border-right:1px solid var(--line);}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:1.1rem;}
.sb-brand{display:flex;align-items:center;gap:11px;padding:2px 2px 0;}
.sb-brand .logo{height:36px;width:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#3b82f6,#38d6ff);font-size:1.1rem;box-shadow:0 8px 20px -6px #38d6ffcc;}
.sb-brand .nm{font-weight:900;font-size:1.08rem;color:#fff;line-height:1.05}
.sb-brand .nm b{background:linear-gradient(90deg,#7cc4ff,#38d6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.sb-brand small{display:block;font-size:.6rem;font-weight:700;color:var(--muted);letter-spacing:.14em;text-transform:uppercase;}
.sb-status{display:inline-flex;align-items:center;gap:7px;font-size:.7rem;font-weight:700;color:#7df0b6;
  background:#0c2a1d;border:1px solid #1c4d3c;border-radius:999px;padding:4px 11px;margin:12px 2px 8px;}
.sb-status i{height:7px;width:7px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;display:inline-block;animation:bl 1.8s infinite;}
.sb-user{display:flex;align-items:center;gap:10px;padding:4px 2px 8px;border-top:1px solid var(--line);margin-top:8px;padding-top:14px;}
.sb-user .av{height:34px;width:34px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#38d6ff);
  display:flex;align-items:center;justify-content:center;color:#04101f;font-weight:800;font-size:.85rem}
.sb-user .u{font-size:.85rem;font-weight:700;color:#e8eefb;line-height:1.05}
.sb-user .r{font-size:.66rem;color:var(--muted)}
hr{border-color:var(--line);}
h1,h2,h3,h4{color:#eef3ff;}
.stApp a{color:#7cc4ff;}

.appbar{display:flex;align-items:center;justify-content:space-between;
  background:linear-gradient(180deg,#0e1a30,#0a1422);border:1px solid var(--line);
  border-radius:16px;padding:11px 18px;box-shadow:0 18px 44px -28px #3b82f6cc;}
.brand{display:flex;align-items:center;gap:12px;}
.brand .logo{height:38px;width:38px;border-radius:11px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#3b82f6,#38d6ff);box-shadow:0 8px 20px -6px #38d6ffcc;font-size:1.2rem;}
.brand .nm{font-weight:900;font-size:1.16rem;color:#fff;letter-spacing:-.3px;line-height:1.05}
.brand .nm b{background:linear-gradient(90deg,#7cc4ff,#38d6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.brand small{display:block;font-size:.64rem;font-weight:700;color:var(--muted);letter-spacing:.14em;text-transform:uppercase;}
.statusdot{display:inline-flex;align-items:center;gap:7px;font-size:.72rem;font-weight:700;color:#7df0b6;
  background:#0c2a1d;border:1px solid #1c4d3c;border-radius:999px;padding:4px 11px;margin-left:6px;}
.statusdot i{height:7px;width:7px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;display:inline-block;animation:bl 1.8s infinite;}
@keyframes bl{50%{opacity:.35}}
.userchip{display:flex;align-items:center;gap:10px;background:#0c1727;border:1px solid var(--line);
  border-radius:999px;padding:5px 6px 5px 14px;}
.userchip .u{font-size:.82rem;font-weight:700;color:#e8eefb;line-height:1.05;text-align:right}
.userchip .r{font-size:.64rem;color:var(--muted)}
.userchip .av{height:32px;width:32px;border-radius:50%;background:linear-gradient(135deg,#3b82f6,#38d6ff);
  display:flex;align-items:center;justify-content:center;color:#04101f;font-weight:800;font-size:.82rem}

.card{background:linear-gradient(165deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;
  padding:17px 19px;position:relative;height:100%;transition:transform .18s,border-color .18s,box-shadow .18s;}
.card::before{content:"";position:absolute;top:0;left:16px;right:16px;height:2px;border-radius:2px;
  background:linear-gradient(90deg,var(--accent),var(--accent2));opacity:.85;}
.card:hover{transform:translateY(-3px);border-color:#2c477b;box-shadow:0 16px 34px -18px #3b82f6aa;}
.kpi{display:flex;align-items:flex-start;justify-content:space-between;}
.kpi .ic{height:40px;width:40px;border-radius:12px;background:#12244480;border:1px solid #244172;
  display:flex;align-items:center;justify-content:center;font-size:1.1rem;color:#7cc4ff;}
.badge{font-size:.7rem;font-weight:800;padding:3px 9px;border-radius:999px;}
.badge.up{color:#7df0b6;background:#0c2a1d;border:1px solid #1c4d3c;}
.badge.dn{color:#ff8d99;background:#2a0f12;border:1px solid #5c1d22;}
.card .v{font-size:1.9rem;font-weight:900;line-height:1.1;margin-top:13px;color:#f2f6ff}
.card .l{font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:.25rem}
.card .s{color:#7d8fae;font-size:.78rem;margin-top:.15rem}
.crit{color:var(--crit)}.high{color:var(--high)}.med{color:var(--med)}.low{color:var(--low)}.ok{color:var(--accent2)}.neu{color:#e8eefb}
.sect{font-size:.74rem;text-transform:uppercase;letter-spacing:.12em;color:#7cc4ff;font-weight:800;margin:6px 0 10px;}
.small{color:#7d8fae;font-size:.82rem}

.steps{display:flex;gap:14px;flex-wrap:wrap}
.step{flex:1 1 200px;background:#0b1730;border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.step .n{height:28px;width:28px;border-radius:8px;background:#10224a;border:1px solid #2c477b;color:#7cc4ff;
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.85rem;margin-bottom:8px}
.step .t{font-weight:700;color:#eaf1ff;font-size:.95rem}
.step .d{color:#9fb3d6;font-size:.83rem;margin-top:3px}

.stButton>button,.stDownloadButton>button{border-radius:11px;font-weight:700;border:1px solid #2c477b;background:#0e1c33;color:#dce8ff;}
.stButton>button:hover{border-color:#3b82f6;color:#fff;}
button[kind="primary"]{background:linear-gradient(90deg,#3b82f6,#38bdf8)!important;color:#04162c!important;border:0!important;box-shadow:0 10px 26px -10px #38bdf8cc;}
[data-testid="stMetric"]{background:#0c1727;border:1px solid var(--line);border-radius:14px;padding:12px 16px;}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;}
.stTextInput input,.stNumberInput input{background:#0b1730!important;border:1px solid #243a63!important;color:#eaf1ff!important;border-radius:11px!important;}
.stTextInput input:focus,.stNumberInput input:focus{border-color:#38d6ff!important;box-shadow:0 0 0 2px #38d6ff33!important;}
.stTextInput label,.stNumberInput label,.stSelectbox label,.stFileUploader label{color:#9fb3d6!important;font-weight:600;}

/* agent stream terminal */
.term{background:#060c16;border:1px solid #1c3350;border-radius:14px;overflow:hidden;box-shadow:0 16px 40px -24px #38d6ff55;}
.term-h{display:flex;align-items:center;gap:8px;padding:9px 14px;background:#0b1626;border-bottom:1px solid #16273f;
  font-size:.74rem;color:#7f97bd;font-weight:700;letter-spacing:.04em;font-family:'JetBrains Mono',monospace}
.term-h .dots{display:flex;gap:6px;margin-right:6px}
.term-h .dots i{height:10px;width:10px;border-radius:50%;display:inline-block}
.term-h .dots i:nth-child(1){background:#ff5c6c}.term-h .dots i:nth-child(2){background:#ffd23f}.term-h .dots i:nth-child(3){background:#22c55e}
.term-b{max-height:360px;overflow-y:auto;padding:12px 16px;font-family:'JetBrains Mono',monospace;font-size:.8rem;line-height:1.55}
.tl{white-space:pre-wrap;word-break:break-word;margin:1px 0;border-left:2px solid transparent;padding-left:8px}
.c-dim{color:#5f7characters}.c-dim{color:#64789a}.c-cy{color:#5fe0ff}.c-am{color:#ffc24d}.c-tx{color:#cdd9e6}.c-gr{color:#6ee7a8}.c-rd{color:#ff7b86}
.cursor{display:inline-block;width:8px;height:14px;background:#5fe0ff;animation:bl 1s steps(2) infinite;vertical-align:middle;border-radius:1px}

/* ioc chips */
.chips{display:flex;flex-wrap:wrap;gap:7px;margin:4px 0 8px}
.chip{font-family:'JetBrains Mono',monospace;font-size:.74rem;padding:4px 10px;border-radius:8px;border:1px solid #284a6e;background:#0c1c30;color:#bcd2f0}
.chip b{color:#5fe0ff;font-weight:700;margin-right:5px;text-transform:uppercase;font-size:.66rem;letter-spacing:.06em}

/* analyst workflow */
.wf{position:relative;margin:.4rem 0 .6rem;padding-left:6px}
.wf-step{position:relative;display:flex;gap:14px;padding:0 0 16px 6px}
.wf-step::before{content:"";position:absolute;left:18px;top:28px;bottom:-2px;width:2px;background:var(--line)}
.wf-step:last-child::before{display:none}
.wf-ic{flex:0 0 26px;height:26px;width:26px;border-radius:50%;background:#10224a;border:1px solid #2c477b;color:#7cc4ff;display:flex;align-items:center;justify-content:center;font-size:.8rem;font-weight:800;z-index:1}
.wf-step.branch .wf-ic{background:#11233f;border-color:#38d6ff;color:#38d6ff}
.wf-body{background:#0b1730;border:1px solid var(--line);border-radius:12px;padding:8px 14px;flex:1}
.wf-t{font-weight:700;color:#eaf1ff;font-size:.92rem}
.wf-d{color:#9fb3d6;font-size:.82rem;margin-top:2px}
.wf-dec{margin:6px 0;padding-left:18px;color:#c9d8f0;font-size:.82rem}
.wf-dec li{margin:2px 0}
.wf-switch{display:inline-block;margin-top:5px;padding:3px 12px;border-radius:999px;font-size:.78rem;font-weight:700;background:#0d2444;border:1px solid #2c477b;color:#7cc4ff}
.wf-switch.crit{color:#ff5c6c;border-color:#5c1d22}.wf-switch.high{color:#ff9f1c;border-color:#5c4a0e}.wf-switch.med{color:#ffd23f}

/* login */
.auth-card{background:linear-gradient(170deg,#0e1c33,#0a1322);border:1px solid #20335c;border-radius:24px;
  padding:34px 34px 26px;box-shadow:0 40px 90px -44px #3b82f6aa;min-height:560px;display:flex;flex-direction:column;justify-content:center;}
.auth-card .badge2{display:inline-flex;align-items:center;gap:8px;font-size:.68rem;font-weight:800;letter-spacing:.12em;
  text-transform:uppercase;color:#7cc4ff;background:#0d2444;border:1px solid #2c477b;border-radius:999px;padding:5px 12px;width:fit-content}
.auth-card h3{margin:16px 0 2px;font-size:1.6rem;font-weight:900;color:#fff;}
.auth-card .sub{color:#9fb3d6;font-size:.92rem;margin-bottom:10px;}
.auth-card .foot{color:#6f82a4;font-size:.74rem;margin-top:16px;text-align:center;line-height:1.5}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
st.session_state.setdefault("evidence", [])
st.session_state.setdefault("result", None)
st.session_state.setdefault("case_id", f"CASE-{datetime.now():%Y%m%d-%H%M}")
st.session_state.setdefault("authenticated", False)
st.session_state.setdefault("username", None)

# ============================================================================
#  BACKEND  (integration logic)
# ============================================================================
def human_size(n):
    n = float(n)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def classify_evidence(name):
    n = name.lower()
    if n.endswith((".e01", ".dd", ".raw", ".img", ".001")):
        return "Disk image"
    if n.endswith((".mem", ".vmem", ".lime", ".dmp")):
        return "Memory capture"
    if n.endswith((".pcap", ".pcapng", ".cap")):
        return "Network capture"
    if n.endswith((".evtx", ".log", ".json", ".csv", ".txt")):
        return "Log / Other"
    return "Other"


def hash_file(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_bytes(data, algo):
    return hashlib.new(algo, data).hexdigest()


def evidence_integrity_statement():
    return ("**Evidence integrity model**\n\n"
            "- Original images are opened **read-only**; source bytes are never written.\n"
            "- The agent runs in Claude Code `dontAsk` mode: only read-only Sleuth Kit tools are "
            "allow-listed; destructive commands (dd, mount, rm, mkfs, tee, ...) are deny-listed.\n"
            "- The image file is set read-only at the OS level (chmod 444).\n"
            "- A SHA-256 baseline is recorded at intake and re-verified after analysis.")


def parse_stream(stdout):
    report, last, tools, usage = "", "", [], {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        t = e.get("type")
        if t == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "text":
                    last = b.get("text", "") or last
                elif b.get("type") == "tool_use":
                    inp = b.get("input", {}) or {}
                    cmd = inp.get("command") or inp.get("file_path") or json.dumps(inp)[:200]
                    tools.append({"Tool": b.get("name", "?"), "Command / Input": cmd})
        elif t == "result":
            report = e.get("result") or last
            usage = e.get("usage", {}) or {}
    return (report or last), tools, usage


# --- original blocking run (kept as a fallback; identical command/args) ---
def run_triage(image_path):
    bundle = f"bundle-{int(time.time())}"
    t0 = time.time()
    _archive_old_bundles()
    c = subprocess.run(["bash", _collector_for(image_path), image_path, bundle], cwd=APP_DIR,
                       capture_output=True, text=True, timeout=1800)
    t_collect = time.time() - t0
    if c.returncode != 0:
        return {"error": "Collector failed:\n" + (c.stdout or "") + "\n" + (c.stderr or "")}
    prompt = _triage_prompt(bundle, image_path)
    p = subprocess.run([CLAUDE_BIN, "-p", prompt, "--permission-mode", "dontAsk", "--max-turns", "10",
                        "--output-format", "stream-json", "--verbose"],
                       cwd=APP_DIR, capture_output=True, text=True, timeout=1800)
    elapsed = time.time() - t0
    os.makedirs(os.path.join(APP_DIR, "logs"), exist_ok=True)
    logp = os.path.join(APP_DIR, "logs", f"{bundle}.jsonl")
    with open(logp, "w") as fh:
        fh.write(p.stdout or "")
    report, tools, usage = parse_stream(p.stdout or "")
    if not report:
        return {"error": "Analysis produced no report:\n" + (p.stdout or "")[:3000] + "\n" + (p.stderr or "")}
    return {"report": report, "tools": tools, "usage": usage, "bundle": bundle,
            "t_collect": t_collect, "elapsed": elapsed, "image": image_path, "log": logp}


_CASE_ISOLATION = (
    ' === CASE ISOLATION (critical) === This is a single, standalone case. Base your '
    'report ONLY on the files inside the bundle named in this prompt. Do NOT read other '
    'directories, other bundle-* folders, or the logs/ folder. Do NOT reference, reuse, or '
    'carry over any finding, IP, MAC, hostname, filename, username, person, or artifact from '
    'any other case. Treat any example or sample report in CLAUDE.md strictly as FORMAT '
    'guidance only - never copy its data, names, or findings into this report. If the bundle '
    'files are empty or inconclusive, say so plainly and report fewer/zero findings - never '
    'fabricate or import findings from elsewhere. When noting the ABSENCE of something '
    '(e.g., no attacker tooling), state it by CATEGORY only - do NOT enumerate specific tool, '
    'product, or file names that are not present in THIS bundle; naming tools from other '
    'scenarios, even to say they are absent, is prohibited.')


_REPORT_FORMAT = (
    ' === REPORT FORMAT === Tag every finding with a severity ID so the counts are '
    'unambiguous: C1, C2, ... for CRITICAL; H1, H2, ... for HIGH; M1, ... for MEDIUM; '
    'L1, ... for LOW (for example: "C1 [CONFIRMED] Cain & Abel - inode 9952"). Where the '
    'bundle evidence supports it, also state the registered owner / primary user account of '
    'the host, any aliases, and the most likely objective or modus operandi (wireless '
    'interception, credential theft, data exfiltration, intrusion) - but ONLY when the bundle '
    'supports it; never guess. Keep the report TIGHT for speed and readability: cite at most '
    '2-3 representative inodes per finding instead of exhaustive lists, and do not enumerate '
    'large directory trees or every index.dat entry - give a count instead (e.g. "+40 more"). '
    'Anything sourced from recycler_info2.txt is a DELETED file recovered from the Recycle Bin '
    '(INFO2): report it as deleted with its pre-deletion path, NOT as present or "staged for use." '
    'Never infer a file\'s identity or product from its name alone - if its function is not '
    'evidenced in the bundle, label it UNVERIFIED and state the purpose is unknown.')


def _archive_old_bundles():
    archive = os.path.join(tempfile.gettempdir(), "findevil-archived-bundles")
    try:
        os.makedirs(archive, exist_ok=True)
        for name in os.listdir(APP_DIR):
            full = os.path.join(APP_DIR, name)
            if name.startswith("bundle-") and os.path.isdir(full):
                shutil.move(full, os.path.join(archive, f"{name}-{int(time.time()*1000)}"))
    except Exception:
        pass


def _collector_for(image_path):
    """Route pcap/pcapng/cap to the network collector; everything else keeps collect.sh."""
    if image_path.lower().endswith((".pcap", ".pcapng", ".cap")):
        return "collect_pcap.sh"
    return "collect.sh"


def _triage_prompt(bundle, image_path):
    if image_path.lower().endswith((".pcap", ".pcapng", ".cap")):
        return (f'The evidence bundle in ./{bundle} was collected from a NETWORK PACKET CAPTURE '
                f'("{image_path}") using tshark. Work FAST. Read ONLY these small files: '
                f'{bundle}/capinfos.txt, {bundle}/protocol_hierarchy.txt, {bundle}/endpoints.txt, '
                f'{bundle}/conversations.txt, {bundle}/dns.txt, {bundle}/http_requests.txt, '
                f'{bundle}/smtp.txt, {bundle}/credentials.txt, {bundle}/dhcp_hostnames.txt, '
                f'{bundle}/emails.txt, {bundle}/indicators.txt. Then write a severity-ranked '
                f'find-evil report per CLAUDE.md focused on NETWORK evidence: suspect hosts '
                f'(IP / MAC / hostname), cleartext credentials, suspicious DNS / HTTP / SMTP / '
                f'webmail activity, data exfiltration or policy violations, and who/what each '
                f'finding implicates. Cite the specific bundle file for every finding and label '
                f'each CONFIRMED / LIKELY / UNVERIFIED. Do NOT run extra shell commands unless a '
                f'CRITICAL finding cannot be supported otherwise (max 2 such).' + _CASE_ISOLATION + _REPORT_FORMAT)
    return (f'The evidence bundle is already collected in ./{bundle}. Work FAST. '
            f'Read ONLY these small files: {bundle}/offset.txt, {bundle}/fsstat.txt, '
            f'{bundle}/indicators.txt, {bundle}/prefetch.txt, {bundle}/recycler_info2.txt. '
            f'Then write the severity-ranked find-evil report directly from them for the image '
            f'at "{image_path}", per CLAUDE.md. Do NOT run mmls/fls/grep or any extra shell '
            f'commands unless a CRITICAL finding truly cannot be supported otherwise (max 2 such). '
            f'Be efficient - finish in as few steps as possible.' + _CASE_ISOLATION + _REPORT_FORMAT)


# --- streaming run: SAME commands/args/log, but yields events as they arrive ---
def run_triage_stream(image_path):
    """Generator yielding event dicts:
       {'status':str} | {'tool':{...}} | {'text':str} | {'error':str} | {'done':result}
       Uses the identical collect.sh + claude -p invocation as run_triage()."""
    bundle = f"bundle-{int(time.time())}"
    t0 = time.time()
    _archive_old_bundles()
    yield {"status": "collect.sh - gathering evidence (read-only)"}
    c = subprocess.run(["bash", _collector_for(image_path), image_path, bundle], cwd=APP_DIR,
                       capture_output=True, text=True, timeout=1800)
    if c.returncode != 0:
        yield {"error": "Collector failed:\n" + (c.stdout or "") + "\n" + (c.stderr or "")}
        return
    t_collect = time.time() - t0
    yield {"status": f"evidence bundle ready in {t_collect:.1f}s -> ./{bundle}"}
    yield {"status": "claude -p --permission-mode dontAsk  (reasoning over bundle)"}

    prompt = _triage_prompt(bundle, image_path)
    os.makedirs(os.path.join(APP_DIR, "logs"), exist_ok=True)
    logp = os.path.join(APP_DIR, "logs", f"{bundle}.jsonl")

    proc = subprocess.Popen(
        [CLAUDE_BIN, "-p", prompt, "--permission-mode", "dontAsk", "--max-turns", "10",
         "--output-format", "stream-json", "--verbose"],
        cwd=APP_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    report, last, tools, usage = "", "", [], {}
    last_text_emit = ""
    raw = []
    logf = open(logp, "w")
    try:
        for line in proc.stdout:
            raw.append(line)
            logf.write(line)
            s = line.strip()
            if not s:
                continue
            try:
                e = json.loads(s)
            except Exception:
                continue
            t = e.get("type")
            if t == "assistant":
                for b in e.get("message", {}).get("content", []):
                    if b.get("type") == "text":
                        txt = b.get("text", "") or ""
                        if txt:
                            last = txt
                            if txt != last_text_emit:
                                last_text_emit = txt
                                yield {"text": txt}
                    elif b.get("type") == "tool_use":
                        inp = b.get("input", {}) or {}
                        cmd = inp.get("command") or inp.get("file_path") or json.dumps(inp)[:200]
                        tool = {"Tool": b.get("name", "?"), "Command / Input": cmd}
                        tools.append(tool)
                        yield {"tool": tool}
            elif t == "result":
                report = e.get("result") or last
                usage = e.get("usage", {}) or {}
    finally:
        proc.wait()
        logf.close()
    elapsed = time.time() - t0
    if not report:
        report = last
    if not report:
        err = "".join(raw)[:3000]
        try:
            err += "\n" + (proc.stderr.read() or "")
        except Exception:
            pass
        yield {"error": "Analysis produced no report:\n" + err}
        return
    yield {"done": {"report": report, "tools": tools, "usage": usage, "bundle": bundle,
                    "t_collect": t_collect, "elapsed": elapsed, "image": image_path, "log": logp}}


def integrity_check():
    f = os.path.join(APP_DIR, "cases", "original.sha256")
    if not os.path.exists(f):
        return None, "No baseline hash recorded (cases/original.sha256)."
    r = subprocess.run(["sha256sum", "-c", "cases/original.sha256"], cwd=APP_DIR,
                       capture_output=True, text=True)
    return (r.returncode == 0), (r.stdout or "") + (r.stderr or "")


def sev_counts(text):
    ids = re.findall(r'(?m)^[\s#>*\-]*\(?\**([CHML])-?\d+\b', text)
    c = Counter(ids)
    if c:
        return c
    sev = {"CRITICAL": "C", "HIGH": "H", "MEDIUM": "M", "LOW": "L"}
    cur, counts, saw = None, Counter(), False
    for raw in text.splitlines():
        head = raw.strip().upper().strip("#*_ :>-")
        if head in sev:
            cur, saw = sev[head], True
            continue
        if cur and re.match(r'^\s*\d+[\.\)]\s+\S', raw):
            counts[cur] += 1
    if saw and sum(counts.values()) > 0:
        return counts
    for k, w in [("C", "CRITICAL"), ("H", "HIGH"), ("M", "MEDIUM"), ("L", "LOW")]:
        counts[k] = len(re.findall(r'\b' + w + r'\b', text))
    return counts


def label_counts(text):
    return Counter(re.findall(r'\b(CONFIRMED|LIKELY|UNVERIFIED)\b', text))


def read_bundle_file(bundle, name, limit=400):
    p = os.path.join(APP_DIR, bundle, name)
    if not os.path.exists(p):
        return None
    with open(p, errors="ignore") as fh:
        lines = fh.readlines()
    return "".join(lines[:limit]), len(lines)


def extract_iocs(text, bundle=None):
    blob = text or ""
    if bundle:
        d = read_bundle_file(bundle, "indicators.txt", 400)
        if d:
            blob += "\n" + d[0]
    iocs = {}

    def add(cat, vals):
        vals = [v for v in dict.fromkeys(vals)]
        if vals:
            iocs[cat] = vals[:8]

    add("IP", re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', blob))
    add("Email", re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', blob))
    add("Hash", re.findall(r'\b[a-fA-F0-9]{32,64}\b', blob))
    add("Tool", [t.lower() for t in re.findall(
        r'\b(cain|pwdump|samdump|nmap|nbtscan|netbus|elsave|netcat|getadmin|sechole|mimikatz|psexec|nc\.exe)\b',
        blob, re.I)])
    add("File", re.findall(r'\b[\w\-]{2,}\.(?:exe|dll|xls|xlsx|doc|docx|bat|ps1|vbs|zip|rar|7z)\b', blob, re.I))
    return iocs


# ============================================================================
#  AUTH
# ============================================================================
def load_credentials():
    path = os.path.join(APP_DIR, "creds.toml")
    creds = {}
    if os.path.exists(path):
        try:
            import tomllib
            with open(path, "rb") as f:
                creds = (tomllib.load(f) or {}).get("credentials", {}) or {}
        except Exception:
            section = None
            for raw in open(path, errors="ignore"):
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("[") and s.endswith("]"):
                    section = s[1:-1].strip()
                    continue
                if section == "credentials" and "=" in s:
                    k, v = s.split("=", 1)
                    creds[k.strip()] = v.strip().strip('"').strip("'")
    if not creds:
        creds = {"analyst": "evil"}
    return {str(k): str(v) for k, v in creds.items()}


def verify_login(username, password, creds):
    if not username or username not in creds:
        return False
    stored = creds[username]
    if stored.startswith("sha256:"):
        return hashlib.sha256(password.encode()).hexdigest() == stored.split(":", 1)[1].strip()
    return password == stored


LOGIN_HERO = """
<div id="lh">
  <canvas id="lhc"></canvas>
  <div class="lh-body">
    <div class="lh-top"><span class="lh-lg">&#128737;</span>
      <span><span class="lh-tx">Find Evil!</span><small>DFIR Triage Platform</small></span></div>
    <h1>Find evil faster<br>than evil moves.</h1>
    <p>An autonomous incident-response analyst that triages disk images, ranks every
       finding by severity, and shows its work &mdash; on read-only evidence.</p>
    <ul>
      <li><i>&#10003;</i> Autonomous triage &mdash; collects, reasons, reports in one run</li>
      <li><i>&#10003;</i> Self-correcting &mdash; CONFIRMED / LIKELY / UNVERIFIED</li>
      <li><i>&#10003;</i> Forensically sound &mdash; read-only, SHA-256 verified</li>
      <li><i>&#10003;</i> Fully traceable &mdash; every finding links to a tool call</li>
    </ul>
    <div class="lh-trust"><span><b>SHA-256</b> verified</span><span><b>Read-only</b> evidence</span><span><b>200+</b> SIFT tools</span></div>
  </div>
</div>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  #lh{position:relative;overflow:hidden;height:560px;border-radius:24px;border:1px solid #1d345c;
     background:radial-gradient(680px 380px at 78% 8%,#1b4fa855,transparent 60%),
                radial-gradient(560px 420px at 8% 100%,#0a6f8d44,transparent 60%),
                linear-gradient(160deg,#0a1426,#0b1f3c 60%,#081626);
     font-family:Inter,system-ui,sans-serif}
  #lhc{position:absolute;inset:0;width:100%;height:100%}
  .lh-body{position:relative;height:100%;padding:42px 40px;display:flex;flex-direction:column;justify-content:space-between}
  .lh-top{display:flex;align-items:center;gap:12px}
  .lh-lg{height:40px;width:40px;border-radius:11px;display:flex;align-items:center;justify-content:center;
     background:linear-gradient(135deg,#3b82f6,#38d6ff);font-size:1.25rem;box-shadow:0 8px 20px -6px #38d6ffcc}
  .lh-tx{font-weight:900;color:#fff;font-size:1.18rem;letter-spacing:-.3px;display:block}
  .lh-top small{font-size:.62rem;letter-spacing:.16em;color:#8fb3e6;text-transform:uppercase;font-weight:700}
  #lh h1{font-size:2.4rem;font-weight:900;line-height:1.08;letter-spacing:-.7px;
     background:linear-gradient(92deg,#fff,#9ed3ff 55%,#38d6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  #lh p{color:#bcccea;font-size:1rem;margin-top:14px;max-width:430px;line-height:1.55}
  #lh ul{list-style:none;margin-top:20px;display:grid;gap:10px}
  #lh li{display:flex;align-items:center;gap:11px;color:#d6e2f6;font-size:.9rem}
  #lh li i{flex:0 0 22px;height:22px;width:22px;border-radius:7px;background:#0d2a44;border:1px solid #1d6f8d;
     color:#5fe0ff;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:900;font-style:normal}
  .lh-trust{display:flex;gap:22px;color:#7f97bd;font-size:.74rem;font-weight:700}
  .lh-trust b{color:#bcd2f0}
</style>
<script>
(function(){
  var c=document.getElementById('lhc'),x=c.getContext('2d'),W,H,dots=[];
  function rs(){W=c.width=c.offsetWidth;H=c.height=c.offsetHeight;}
  rs();window.addEventListener('resize',rs);
  for(var i=0;i<46;i++){dots.push({x:Math.random(),y:Math.random(),s:Math.random()*1.6+.4,v:Math.random()*.0006+.0002});}
  function loop(){
    x.clearRect(0,0,W,H);
    for(var i=0;i<dots.length;i++){var d=dots[i];d.y-=d.v;if(d.y<0)d.y=1;
      x.beginPath();x.arc(d.x*W,d.y*H,d.s,0,7);x.fillStyle='rgba(90,200,255,'+(.18+d.s*.18)+')';x.fill();}
    for(var i=0;i<dots.length;i++){for(var j=i+1;j<dots.length;j++){
      var a=dots[i],b=dots[j],dx=(a.x-b.x)*W,dy=(a.y-b.y)*H,dist=Math.sqrt(dx*dx+dy*dy);
      if(dist<120){x.beginPath();x.moveTo(a.x*W,a.y*H);x.lineTo(b.x*W,b.y*H);
        x.strokeStyle='rgba(60,130,220,'+(.10*(1-dist/120))+')';x.stroke();}}}
    requestAnimationFrame(loop);
  }
  loop();
})();
</script>
"""


def render_login():
    # Force the two login columns to stay side-by-side (don't wrap/stack) and
    # vertically center them so the form sits beside the brand panel.
    st.markdown("""
    <style>
      [data-testid='stSidebar']{display:none!important;}
      div[data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;align-items:center!important;gap:30px!important;}
      div[data-testid="stHorizontalBlock"]>div[data-testid="column"]{min-width:0!important;}
      /* style the real right-hand column as the login card (widgets live inside it) */
      div[data-testid="stHorizontalBlock"]>div[data-testid="column"]:last-child{
        background:linear-gradient(170deg,#0e1c33,#0a1322);border:1px solid #20335c;border-radius:24px;
        padding:34px 32px 28px!important;box-shadow:0 40px 90px -44px #3b82f6aa;}
      div[data-testid="stHorizontalBlock"]>div[data-testid="column"]:last-child [data-testid="stForm"]{
        border:none!important;padding:0!important;}
    </style>""", unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        components.html(LOGIN_HERO, height=560)
    with right:
        st.markdown("<span class='badge2'>🔐 Secure sign-in</span>", unsafe_allow_html=True)
        st.markdown("<h3>Welcome back</h3><div class='sub'>Sign in to your incident-response workspace.</div>",
                    unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            u = st.text_input("Username", placeholder="analyst")
            p = st.text_input("Password", type="password", placeholder="••••••••")
            ok = st.form_submit_button("Sign in  →", type="primary", use_container_width=True)
        if ok:
            if verify_login((u or "").strip(), p or "", load_credentials()):
                st.session_state.authenticated = True
                st.session_state.username = (u or "").strip()
                _rerun()
            else:
                st.error("Invalid credentials. Check **creds.toml** for the configured users.")
        st.markdown("<div class='foot'>Credentials are read from <code>creds.toml</code>.<br>"
                    "Evidence is always opened read-only.</div>", unsafe_allow_html=True)


# ============================================================================
#  CHARTS / WIDGETS
# ============================================================================
def severity_donut(sc):
    names = ["Critical", "High", "Medium", "Low"]
    keys = ["C", "H", "M", "L"]
    vals = [sc.get(k, 0) for k in keys]
    cols = ["#ff4b5c", "#ff9f1c", "#ffd23f", "#4dabf7"]
    if HAS_PLOTLY and sum(vals) > 0:
        fig = go.Figure(go.Pie(labels=names, values=vals, hole=.62, sort=False,
                               marker=dict(colors=cols, line=dict(color="#070b16", width=3)), textinfo="value"))
        fig.update_layout(height=260, margin=dict(t=8, b=8, l=8, r=8), paper_bgcolor="rgba(0,0,0,0)",
                          font_color="#cdd9e6", legend=dict(orientation="h", y=-.1),
                          annotations=[dict(text=f"<b>{sum(vals)}</b><br>findings", x=.5, y=.5,
                                            showarrow=False, font_size=15, font_color="#e8eefb")])
        st.plotly_chart(fig, use_container_width=True)
    else:
        cs = st.columns(4)
        for col, (nm, k, cl) in zip(cs, [("Critical", "C", "crit"), ("High", "H", "high"),
                                         ("Medium", "M", "med"), ("Low", "L", "low")]):
            col.markdown(f"<div class='card'><div class='v {cl}'>{sc.get(k, 0)}</div>"
                         f"<div class='l'>{nm}</div></div>", unsafe_allow_html=True)


def label_bar(lc):
    if HAS_PLOTLY and sum(lc.values()) > 0:
        names = ["CONFIRMED", "LIKELY", "UNVERIFIED"]
        vals = [lc.get(n, 0) for n in names]
        cols = ["#22c55e", "#ffd23f", "#ff9f1c"]
        fig = go.Figure(go.Bar(x=names, y=vals, marker_color=cols, text=vals, textposition="outside",
                               marker_line_color="#070b16", marker_line_width=1))
        fig.update_layout(height=240, margin=dict(t=18, b=8, l=8, r=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font_color="#cdd9e6", yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)
    else:
        cs = st.columns(3)
        for col, n in zip(cs, ["CONFIRMED", "LIKELY", "UNVERIFIED"]):
            col.metric(n.title(), lc.get(n, 0))


def ioc_graph(iocs):
    catcolor = {"IP": "#4dabf7", "Email": "#ffd23f", "Hash": "#b388ff",
                "Tool": "#ff5c6c", "File": "#22c55e", "Domain": "#38d6ff"}
    cats = list(iocs.keys())
    if not cats:
        st.caption("No structured indicators detected in this report.")
        return
    if not HAS_PLOTLY:
        for cat in cats:
            chips = "".join(f"<span class='chip'><b>{cat}</b>{_esc(v)}</span>" for v in iocs[cat])
            st.markdown(f"<div class='chips'>{chips}</div>", unsafe_allow_html=True)
        return

    ex, ey = [], []
    nx_, ny_, ncol, nsz, ntxt, nhov = [], [], [], [], [], []
    nx_.append(0); ny_.append(0); ncol.append("#3b82f6"); nsz.append(36); ntxt.append("CASE"); nhov.append("Case root")
    n = len(cats)
    for i, cat in enumerate(cats):
        ang = 2 * math.pi * i / max(1, n)
        cx, cy = math.cos(ang) * 2.5, math.sin(ang) * 2.5
        ex += [0, cx, None]; ey += [0, cy, None]
        nx_.append(cx); ny_.append(cy); ncol.append(catcolor.get(cat, "#7cc4ff"))
        nsz.append(24); ntxt.append(f"{cat} ({len(iocs[cat])})"); nhov.append(cat)
        vals = iocs[cat]
        m = len(vals)
        for j, v in enumerate(vals):
            a2 = ang + (j - (m - 1) / 2.0) * (0.9 / max(1, m))
            vx, vy = math.cos(a2) * 4.6, math.sin(a2) * 4.6
            ex += [cx, vx, None]; ey += [cy, vy, None]
            nx_.append(vx); ny_.append(vy); ncol.append(catcolor.get(cat, "#7cc4ff"))
            nsz.append(11); ntxt.append(""); nhov.append(v)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ex, y=ey, mode="lines", line=dict(color="#21436e", width=1), hoverinfo="none"))
    fig.add_trace(go.Scatter(x=nx_, y=ny_, mode="markers+text", text=ntxt, textposition="top center",
                             textfont=dict(color="#cdd9e6", size=11),
                             marker=dict(size=nsz, color=ncol, line=dict(color="#070b16", width=1.5)),
                             hovertext=nhov, hoverinfo="text"))
    fig.update_layout(height=430, showlegend=False, margin=dict(t=10, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    st.plotly_chart(fig, use_container_width=True)


def timeline_chart(text):
    seen, rows = set(), []
    for m in re.finditer(r'(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}:\d{2}(?::\d{2})?))?', text or ""):
        key = m.group(0)
        if key in seen:
            continue
        seen.add(key)
        start = max(0, m.start() - 60)
        ctx = re.sub(r'\s+', ' ', text[start:m.start()]).strip()[-46:]
        rows.append({"when": m.group(1) + ("T" + m.group(2) if m.group(2) else ""),
                     "label": ctx or "event"})
    if len(rows) < 3 or not HAS_PLOTLY:
        return False
    df = pd.DataFrame(rows[:14])
    df["dt"] = pd.to_datetime(df["when"], errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")
    if len(df) < 3:
        return False
    ys = [(1 if i % 2 else -1) for i in range(len(df))]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["dt"], y=[0] * len(df), mode="lines",
                             line=dict(color="#21436e", width=2), hoverinfo="none"))
    fig.add_trace(go.Scatter(x=df["dt"], y=ys, mode="markers",
                             marker=dict(size=13, color="#38d6ff", line=dict(color="#070b16", width=1)),
                             hovertext=[f"{w} — {l}" for w, l in zip(df['when'], df['label'])], hoverinfo="text"))
    fig.update_layout(height=210, showlegend=False, margin=dict(t=10, b=10, l=10, r=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      yaxis=dict(visible=False, range=[-2, 2]),
                      xaxis=dict(color="#9fb3d6", gridcolor="#16273f"))
    st.plotly_chart(fig, use_container_width=True)
    return True


def kpi_card(icon, value, label, sub="", trend=None, vcls="neu"):
    badge = ""
    if trend is not None:
        cls = "up" if trend >= 0 else "dn"
        arrow = "▲" if trend >= 0 else "▼"
        badge = f"<span class='badge {cls}'>{arrow} {abs(trend):.2f}%</span>"
    return (f"<div class='card'><div class='kpi'><span class='ic'>{icon}</span>{badge}</div>"
            f"<div class='v {vcls}'>{value}</div><div class='l'>{label}</div>"
            f"<div class='s'>{sub}</div></div>")


def analyst_workflow(res):
    b = res["bundle"]
    report = res.get("report", "")

    def rd(n):
        d = read_bundle_file(b, n, 400)
        return d[0] if d else ""

    part = rd("partitions.txt")
    fss = rd("fsstat.txt")
    ind = rd("indicators.txt")
    off = rd("offset.txt").strip() or "?"
    img = res["image"].lower()
    if img.endswith((".e01", ".e02")):
        imgtype = "EnCase / Expert Witness (.E01)"
    elif img.endswith((".001", ".dd", ".raw", ".img")):
        imgtype = "Raw / split image (dd)"
    else:
        imgtype = "Disk image"
    fstype = "NTFS" if re.search(r"NTFS", fss + part, re.I) else ("FAT" if re.search(r"FAT", fss + part, re.I) else "filesystem")
    sm = re.search(r"Serial\s*Number?\s*[:=]?\s*([0-9A-Fa-f]{8,})", fss)
    serial = sm.group(1) if sm else ""
    toolkit = bool(re.search(r"\b(cain|pwdump|samdump|nmap|nbtscan|enum\.exe|netbus|elsave|nc\.exe|netcat|getadmin|sechole)\b", ind, re.I))
    pf = rd("prefetch.txt")
    has_pf = bool(pf.strip())
    has_doc = bool(re.search(r"\.xls|\.doc|spreadsheet|sensitive document", ind, re.I))
    has_mail = ("EXFIL CANDIDATE" in ind) or bool(re.search(r"@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", ind))
    m = re.search(r"[Cc]ase type[:\s-]*([A-Za-z]+)", report)
    rep_track = m.group(1).upper() if m else ""
    if "INTRUS" in rep_track or (not rep_track and toolkit):
        dec = ["Attacker toolkit present (cain / pwdump / nmap ...)"]
        if has_pf:
            dec.append("Prefetch confirms tool execution")
        switch = "INTRUSION workflow"
        tcol = "crit"
    elif "EXFIL" in rep_track or has_doc or has_mail:
        dec = ["NO attacker tools found"]
        if has_doc:
            dec.append("Sensitive spreadsheet found")
        if has_mail:
            dec.append("Email artifacts present")
        switch = "EXFILTRATION workflow"
        tcol = "high"
    else:
        dec = ["No dominant attacker tooling", "Falling back to general triage"]
        switch = "GENERAL triage"
        tcol = "med"
    steps = [("Detect image type", imgtype),
             ("Find partitions", f"filesystem offset = sector {off}"),
             ("Extract filesystem metadata", f"{fstype}, Windows host" + (f" - volume serial {serial}" if serial else "")),
             ("Determine investigation type", "__DECISION__"),
             (f"Run {switch.split()[0]} analysis", "track-specific reasoning over the evidence bundle"),
             ("Self-correct & label findings", "CONFIRMED / LIKELY / UNVERIFIED, each cited to an inode"),
             ("Compose report", f"{round(res['elapsed'])}s, {len(res['tools'])} tool calls")]
    out = "<div class='wf'>"
    for i, (t, d) in enumerate(steps, 1):
        if d == "__DECISION__":
            bl = "".join(f"<li>{x}</li>" for x in dec)
            body = (f"<div class='wf-t'>{t}</div><div class='wf-d'>Decision:</div>"
                    f"<ul class='wf-dec'>{bl}</ul><span class='wf-switch {tcol}'>&#8594; Switching to {switch}</span>")
            cls = "wf-step branch"
        else:
            body = f"<div class='wf-t'>{t}</div><div class='wf-d'>{d}</div>"
            cls = "wf-step done"
        out += f"<div class='{cls}'><div class='wf-ic'>{i}</div><div class='wf-body'>{body}</div></div>"
    out += "</div>"
    st.markdown("##### Analyst workflow")
    st.markdown(out, unsafe_allow_html=True)


# ============================================================================
#  SIDEBAR + NAV
# ============================================================================
def render_sidebar():
    user = st.session_state.username or "analyst"
    initials = "".join([w[0] for w in re.split(r"[.\s_-]+", user) if w][:2]).upper() or "A"
    pages = ["Dashboard", "Evidence", "Analyze", "Findings", "Logs"]
    with st.sidebar:
        st.markdown(
            "<div class='sb-brand'><span class='logo'>🛡️</span>"
            "<div><div class='nm'>Find <b>Evil!</b></div><small>DFIR Triage</small></div></div>"
            "<div class='sb-status'><i></i> Live &middot; Read-only</div>", unsafe_allow_html=True)
        if HAS_MENU:
            page = option_menu(
                None, pages,
                icons=["grid-1x2", "hdd-stack", "cpu", "clipboard2-data", "terminal"],
                orientation="vertical", default_index=0,
                styles={"container": {"background-color": "transparent", "padding": "2px 0"},
                        "nav-link": {"font-size": "14px", "font-weight": "600", "color": "#9fb0c9",
                                     "padding": "10px 14px", "border-radius": "10px", "margin": "3px 0",
                                     "--hover-color": "#16233f"},
                        "nav-link-selected": {"background": "linear-gradient(90deg,#3b82f6,#38bdf8)",
                                              "color": "#fff", "font-weight": "700"},
                        "icon": {"color": "#7cc4ff", "font-size": "15px"}})
        else:
            page = st.radio("Navigate", pages, label_visibility="collapsed")
        st.markdown(
            f"<div class='sb-user'><span class='av'>{_esc(initials)}</span>"
            f"<div><div class='u'>{_esc(user)}</div><div class='r'>Incident Responder</div></div></div>",
            unsafe_allow_html=True)
        if st.button("Log out", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.username = None
            _rerun()
    return page


# ============================================================================
#  PAGES
# ============================================================================
DASH_HERO = """
<div id="dh"><canvas id="dhc"></canvas>
  <div class="dh-l">
    <h1>Find Evil!</h1>
    <p>An AI agent that thinks like a senior analyst &mdash; sequences its approach, notices
       when something doesn't add up, and self-corrects, at machine speed.</p>
    <div class="dh-tags"><span>Read-only evidence</span><span>Self-correction</span>
      <span>Adaptive triage</span><span>Full traceability</span></div>
  </div>
  <div class="dh-r"><svg viewBox="0 0 200 200" class="radar">
    <circle cx="100" cy="100" r="92" class="rg"/><circle cx="100" cy="100" r="62" class="rg"/>
    <circle cx="100" cy="100" r="32" class="rg"/>
    <line x1="100" y1="8" x2="100" y2="192" class="rg"/><line x1="8" y1="100" x2="192" y2="100" class="rg"/>
    <g class="sweep"><path d="M100 100 L100 8 A92 92 0 0 1 178 60 Z" fill="url(#g)"/></g>
    <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#38d6ff" stop-opacity=".55"/><stop offset="100%" stop-color="#38d6ff" stop-opacity="0"/>
    </linearGradient></defs>
    <circle cx="148" cy="64" r="4" class="blip"/><circle cx="70" cy="140" r="3" class="blip b2"/>
    <circle cx="120" cy="150" r="3" class="blip b3"/>
  </svg></div>
</div>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  #dh{position:relative;overflow:hidden;height:212px;border-radius:20px;border:1px solid #20335c;
     display:flex;align-items:center;justify-content:space-between;padding:24px 30px;
     background:linear-gradient(125deg,#0c1a33,#102a4d 55%,#0b1f3f);font-family:Inter,system-ui,sans-serif}
  #dhc{position:absolute;inset:0;width:100%;height:100%;opacity:.6}
  .dh-l{position:relative;max-width:62%}
  #dh h1{font-size:2.1rem;font-weight:900;letter-spacing:-.6px;
     background:linear-gradient(90deg,#fff 6%,#7cc4ff 52%,#38d6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  #dh p{color:#b7c7e6;font-size:.98rem;margin-top:8px;line-height:1.5}
  .dh-tags{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}
  .dh-tags span{font-size:.72rem;font-weight:700;color:#9fd0ff;border:1px solid #2c4a7e;background:#0e244466;border-radius:999px;padding:5px 12px}
  .dh-r{position:relative}
  .radar{height:170px;width:170px}
  .radar .rg{fill:none;stroke:#2c4a7e;stroke-width:1;opacity:.6}
  .radar .sweep{transform-origin:100px 100px;animation:sw 3.4s linear infinite}
  @keyframes sw{to{transform:rotate(360deg)}}
  .radar .blip{fill:#5fe0ff;animation:bp 3.4s ease-in-out infinite}
  .radar .b2{animation-delay:1.1s}.radar .b3{animation-delay:2.2s}
  @keyframes bp{0%,100%{opacity:.15}40%{opacity:1}}
</style>
<script>
(function(){var c=document.getElementById('dhc'),x=c.getContext('2d'),W,H,p=[];
function rs(){W=c.width=c.offsetWidth;H=c.height=c.offsetHeight;}rs();window.addEventListener('resize',rs);
for(var i=0;i<28;i++)p.push({x:Math.random(),y:Math.random(),s:Math.random()*1.4+.3,v:Math.random()*.0005+.0002});
function loop(){x.clearRect(0,0,W,H);for(var i=0;i<p.length;i++){var d=p[i];d.x+=d.v;if(d.x>1)d.x=0;
 x.beginPath();x.arc(d.x*W,d.y*H,d.s,0,7);x.fillStyle='rgba(90,200,255,.5)';x.fill();}requestAnimationFrame(loop);}loop();})();
</script>
"""


def page_dashboard():
    components.html(DASH_HERO, height=224)
    st.write("")
    cards = [("⚡", "7 min", "Adversary breakout", "fastest observed", -3.40),
             ("🤖", "60 sec", "Autonomous priv-esc", "Horizon3 agent", -1.80),
             ("🚀", "47x", "AI vs human speed", "MIT 2024", 12.50),
             ("🧰", "200+", "SIFT tools", "one platform", 0.70)]
    cs = st.columns(4)
    for col, (ic, val, lab, sub, tr) in zip(cs, cards):
        col.markdown(kpi_card(ic, val, lab, sub, trend=tr), unsafe_allow_html=True)

    st.write("")
    res = st.session_state.result
    if res:
        sc = sev_counts(res["report"])
        st.markdown("<div class='sect'>Latest run</div>", unsafe_allow_html=True)
        cs = st.columns(4)
        cs[0].markdown(kpi_card("⏱️", f"{round(res['elapsed'])}s", "Total time", "collect + analyze"), unsafe_allow_html=True)
        cs[1].markdown(kpi_card("🔧", len(res['tools']), "Tool calls", "fully traceable"), unsafe_allow_html=True)
        cs[2].markdown(kpi_card("🚨", sc.get('C', 0), "Critical", "severity-ranked", vcls="crit"), unsafe_allow_html=True)
        cs[3].markdown(kpi_card("⚠️", sc.get('H', 0), "High", "severity-ranked", vcls="high"), unsafe_allow_html=True)
        st.caption("Open the **Findings** tab for the full report, IOC graph and timeline.")
    else:
        st.markdown("<div class='sect'>How it works</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='steps'>"
            "<div class='step'><div class='n'>1</div><div class='t'>Register evidence</div>"
            "<div class='d'>Add a disk image by path. It's hashed (SHA-256/MD5) and opened read-only.</div></div>"
            "<div class='step'><div class='n'>2</div><div class='t'>Run the agent</div>"
            "<div class='d'>collect.sh gathers artifacts, then the agent reasons over the bundle - live.</div></div>"
            "<div class='step'><div class='n'>3</div><div class='t'>Review findings</div>"
            "<div class='d'>Severity-ranked report with confidence labels and a full, traceable tool log.</div></div>"
            "</div>", unsafe_allow_html=True)
        st.info("No analysis yet — go to **Evidence** to register an image, then **Analyze** to run the agent.", icon="🧭")


def page_intake():
    st.subheader("Evidence Intake & Integrity")
    st.caption("Register a real image by path (streamed hashing, multi-GB safe) or upload a small file.")
    default_img = "/home/ubuntu/Desktop/4Dell Latitude CPi.E01"
    path = st.text_input("Path to evidence on this workstation", value=default_img)
    c1, c2 = st.columns(2)
    if c1.button("Register by path", type="primary", use_container_width=True):
        if not os.path.exists(path):
            st.error("File not found: " + path)
        else:
            with st.spinner("Hashing (read-only)..."):
                size = os.path.getsize(path)
                st.session_state.evidence.append({
                    "Filename": os.path.basename(path), "Path": path,
                    "Type": classify_evidence(path), "Size": human_size(size),
                    "SHA-256": hash_file(path, "sha256"), "MD5": hash_file(path, "md5"),
                    "Ingested (UTC)": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "Access": "read-only"})
            st.success("Registered with verified hashes.")
    up = c2.file_uploader("...or upload a small artifact", type=None, accept_multiple_files=True)
    if c2.button("Ingest uploaded", use_container_width=True):
        for f in up or []:
            d = f.getvalue()
            st.session_state.evidence.append({
                "Filename": f.name, "Path": "(uploaded)", "Type": classify_evidence(f.name),
                "Size": human_size(len(d)), "SHA-256": hash_bytes(d, "sha256"), "MD5": hash_bytes(d, "md5"),
                "Ingested (UTC)": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), "Access": "read-only"})
        st.success("Uploaded artifacts ingested.")
    ev = st.session_state.evidence
    if not ev:
        st.info("No evidence yet. Register an image to begin.", icon="📥")
        return
    st.markdown("##### Chain of custody")
    st.dataframe(pd.DataFrame(ev).drop(columns=["Path"], errors="ignore"),
                 use_container_width=True, hide_index=True)
    with st.expander("Evidence integrity model"):
        st.markdown(evidence_integrity_statement())
    if st.button("Clear evidence"):
        st.session_state.evidence = []
        _rerun()


EVIDENCE_PATTERNS = {
    "Disk image": ("*.E01", "*.dd", "*.001", "*.raw", "*.img"),
    "Network capture": ("*.pcap", "*.pcapng", "*.cap"),
}


def _evidence_choices(kind):
    """Registered evidence of the given type, plus matching files on ~/Desktop."""
    paths = [e["Path"] for e in st.session_state.evidence
             if e.get("Type") == kind and e.get("Path", "").startswith("/")]
    for pat in EVIDENCE_PATTERNS.get(kind, ()):
        paths += glob.glob(os.path.expanduser("~/Desktop/" + pat))
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def page_agent_run():
    st.subheader("Autonomous Agent Run")
    st.caption("Runs collect.sh (read-only), then streams Claude's reasoning live as it analyzes the bundle per CLAUDE.md.")
    kind = st.radio("Evidence type", ["Disk image", "Network capture"], horizontal=True,
                    help="Switches the dropdown between disk images (.E01/.dd/.raw/...) and packet captures (.pcap/.pcapng/.cap).")
    choices = _evidence_choices(kind)
    defaults = {"Disk image": "/home/ubuntu/Desktop/4Dell Latitude CPi.E01",
                "Network capture": "/home/ubuntu/Desktop/capture.pcap"}
    default_path = defaults.get(kind, "")
    if choices:
        idx = choices.index(default_path) if default_path in choices else 0
        image = st.selectbox(f"{kind} to analyze", choices, index=idx)
    else:
        image = st.text_input(f"{kind} path", value=default_path)
        st.caption("No matching files on ~/Desktop or in registered evidence — type a full path, "
                   "or add it in the **Evidence** tab.")
    if kind == "Network capture":
        st.info("Network-capture triage requires your `collect.sh` / `CLAUDE.md` to support pcap input. "
                "The disk-image workflow is the validated path.", icon="📡")

    if st.button("Run triage agent", type="primary"):
        if not os.path.exists(image):
            st.error("File not found: " + image)
        else:
            metric_ph = st.empty()
            term_ph = st.empty()
            feed = ["<span class='c-dim'>$ ./collect.sh \"" + _esc(os.path.basename(image)) + "\" (read-only)</span>"]
            ntools = [0]

            def render():
                body = "".join("<div class='tl'>" + ln + "</div>" for ln in feed[-260:])
                term_ph.markdown(
                    "<div class='term'><div class='term-h'><span class='dots'><i></i><i></i><i></i></span>"
                    "find-evil · agent stream</div><div class='term-b'>" + body +
                    "<span class='cursor'></span></div></div>", unsafe_allow_html=True)

            def metrics(done=False):
                state = "complete" if done else "running"
                color = "ok" if done else "neu"
                metric_ph.markdown(
                    "<div style='display:flex;gap:10px'>"
                    + kpi_card("📡", state, "Agent state", "live stream", vcls=color)
                    + kpi_card("🔧", ntools[0], "Tool calls", "so far")
                    + "</div>", unsafe_allow_html=True)

            metrics(); render()
            result = error = None
            try:
                for ev in run_triage_stream(image):
                    if "status" in ev:
                        feed.append("<span class='c-cy'>▸ " + _esc(ev["status"]) + "</span>")
                    elif "tool" in ev:
                        ntools[0] += 1
                        feed.append("<span class='c-am'>⚙ " + _esc(ev["tool"]["Tool"]) + "</span> "
                                    "<span class='c-dim'>" + _esc(ev["tool"]["Command / Input"][:150]) + "</span>")
                        metrics()
                    elif "text" in ev:
                        snippet = re.sub(r"\s+", " ", ev["text"]).strip()[:300]
                        if snippet:
                            feed.append("<span class='c-tx'>💭 " + _esc(snippet) + "</span>")
                    elif "error" in ev:
                        error = ev["error"]; break
                    elif "done" in ev:
                        result = ev["done"]; break
                    render()
            except Exception as e:
                error = f"Stream error: {e}"

            if error:
                feed.append("<span class='c-rd'>✗ " + _esc(error[:300]) + "</span>"); render()
                st.error(error)
            elif result:
                st.session_state.result = result
                feed.append("<span class='c-gr'>✓ report composed — "
                            + str(round(result["elapsed"])) + "s · "
                            + str(len(result["tools"])) + " tool calls · self-corrected</span>")
                render(); metrics(done=True)

    res = st.session_state.result
    if res:
        st.divider()
        sc = sev_counts(res["report"])
        c = st.columns(4)
        c[0].markdown(kpi_card("⏱️", f"{round(res['elapsed'])}s", "Total time", "collect + analyze"), unsafe_allow_html=True)
        c[1].markdown(kpi_card("🔧", len(res['tools']), "Tool calls", "fully traceable"), unsafe_allow_html=True)
        c[2].markdown(kpi_card("🚨", sc.get('C', 0), "Critical", "severity-ranked", vcls="crit"), unsafe_allow_html=True)
        c[3].markdown(kpi_card("⚠️", sc.get('H', 0), "High", "severity-ranked", vcls="high"), unsafe_allow_html=True)
        analyst_workflow(res)
        st.markdown("##### Report")
        st.markdown(res["report"])


def page_findings():
    st.subheader("Findings & IOCs")
    res = st.session_state.result
    if not res:
        st.info("Run the agent first (Analyze tab).", icon="ℹ️")
        return
    report = res["report"]
    sc = sev_counts(report)
    lc = label_counts(report)
    a, b = st.columns([1, 1])
    with a:
        st.markdown("**Severity breakdown**")
        severity_donut(sc)
    with b:
        st.markdown("**Self-correction labels**")
        label_bar(lc)

    iocs = extract_iocs(report, res.get("bundle"))
    st.markdown("<div class='sect'>Indicators of compromise</div>", unsafe_allow_html=True)
    if iocs:
        chips = ""
        for cat, vals in iocs.items():
            for v in vals:
                chips += f"<span class='chip'><b>{cat}</b>{_esc(v)}</span>"
        st.markdown(f"<div class='chips'>{chips}</div>", unsafe_allow_html=True)
        ioc_graph(iocs)
    else:
        st.caption("No structured indicators detected in this report.")

    st.markdown("<div class='sect'>Event timeline</div>", unsafe_allow_html=True)
    if not timeline_chart(report):
        st.caption("Not enough dated events in this report to plot a timeline.")

    st.divider()
    st.download_button("Download report (.md)", report, file_name=f"{st.session_state.case_id}_findings.md")
    st.markdown(report)


def page_logs():
    st.subheader("Agent Execution Logs")
    res = st.session_state.result
    if not res:
        st.info("Run the agent first (Analyze tab).", icon="ℹ️")
        return
    tools = res["tools"]
    df = pd.DataFrame(tools) if tools else pd.DataFrame(columns=["Tool", "Command / Input"])
    c1, c2 = st.columns(2)
    c1.metric("Tool calls", len(df))
    c2.metric("Wall time", f"{round(res['elapsed'])}s")
    if tools and HAS_PLOTLY:
        vc = df["Tool"].value_counts()
        fig = go.Figure(go.Bar(x=list(vc.index), y=list(vc.values), marker_color="#38bdf8",
                               text=list(vc.values), textposition="outside",
                               marker_line_color="#070b16", marker_line_width=1))
        fig.update_layout(height=260, margin=dict(t=18, b=8, l=8, r=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font_color="#cdd9e6")
        st.plotly_chart(fig, use_container_width=True)
    st.caption("Every tool call Claude made this run (traceable from any finding).")
    st.dataframe(df, use_container_width=True, hide_index=True)
    if os.path.exists(res["log"]):
        with open(res["log"]) as fh:
            st.download_button("Download raw stream log (.jsonl)", fh.read(),
                               file_name=os.path.basename(res["log"]))

    st.divider()
    st.subheader("Accuracy Self-Assessment")
    lc = label_counts(res["report"])
    label_bar(lc)
    st.caption("From the agent's own self-correction labels in this run.")
    st.markdown("##### Compare vs Protocol SIFT baseline")
    b1, b2 = st.columns(2)
    base_h = b1.number_input("Baseline hallucinated claims", min_value=0, value=0)
    base_fp = b2.number_input("Baseline false positives", min_value=0, value=0)
    comp = pd.DataFrame({"Metric": ["Unverified/flagged", "Confirmed"],
                         "This agent": [lc.get("UNVERIFIED", 0), lc.get("CONFIRMED", 0)],
                         "Baseline (you set)": [base_h, base_fp]})
    st.dataframe(comp, use_container_width=True, hide_index=True)
    st.markdown("##### Evidence integrity")
    ok, msg = integrity_check()
    if ok:
        st.success("Image SHA-256 matches baseline - evidence not modified.")
    elif ok is None:
        st.warning(msg)
    else:
        st.error("Hash mismatch.")
    st.code(msg or "")
    st.markdown(evidence_integrity_statement())


ROUTES = {"Dashboard": page_dashboard, "Evidence": page_intake, "Analyze": page_agent_run,
          "Findings": page_findings, "Logs": page_logs}

# ============================================================================
#  ENTRY
# ============================================================================
if not st.session_state.authenticated:
    render_login()
    st.stop()

page = render_sidebar()
ROUTES[page]()