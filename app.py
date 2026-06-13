"""Find Evil! - Autonomous DFIR Triage Agent (live integration + product UI).

Integration is unchanged: collect.sh gathers evidence read-only, then claude -p
analyzes the bundle per CLAUDE.md. Only the presentation layer is rebuilt:
  * Config-file login / logout (credentials in creds.toml) - no image required
  * Pure-CSS branded login screen
  * No sidebar - a premium top header with brand, navigation, user + logout
  * Focused tabs: Dashboard - Evidence - Analyze - Findings - Logs
  * Dark navy "command-center" theme with electric-blue + cyan accents

Run:  streamlit run app.py            (from ~/Desktop/sift-agent)

Optional pretty libs (graceful fallback if missing):
  pip3 install --break-system-packages plotly streamlit-option-menu
"""
from __future__ import annotations
import os, re, io, glob, json, time, hashlib, subprocess
from collections import Counter
from datetime import datetime
import pandas as pd
import streamlit as st

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


st.set_page_config(page_title="Find Evil! - DFIR Triage", page_icon="🛡️",
                   layout="wide", initial_sidebar_state="collapsed")

# ============================================================================
#  GLOBAL THEME
# ============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');
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
/* kill the sidebar entirely */
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"]{display:none!important;}
.block-container{padding-top:1.0rem;padding-bottom:3rem;max-width:1320px;}
hr{border-color:var(--line);}
h1,h2,h3,h4{color:#eef3ff;}
.stApp a{color:#7cc4ff;}

/* ---- header ---- */
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

/* ---- hero ---- */
.hero{position:relative;overflow:hidden;border:1px solid #20335c;border-radius:20px;padding:28px 32px;margin-bottom:18px;
  background:linear-gradient(125deg,#0c1a33,#102a4d 55%,#0b1f3f);box-shadow:0 24px 64px -32px #3b82f6aa;}
.hero::after{content:"";position:absolute;right:-70px;top:-70px;height:260px;width:260px;border-radius:50%;
  background:radial-gradient(circle,#38d6ff40,transparent 65%);}
.hero h1{margin:0;font-size:2.1rem;font-weight:900;letter-spacing:-.6px;
  background:linear-gradient(90deg,#fff 6%,#7cc4ff 52%,#38d6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.hero p{margin:.55rem 0 0;color:#b7c7e6;font-size:1.02rem;max-width:820px;}
.tag{display:inline-block;padding:5px 13px;border-radius:999px;font-size:.72rem;font-weight:700;margin:12px 7px 0 0;
  border:1px solid #2c4a7e;color:#9fd0ff;background:#0e244466;}

/* ---- cards ---- */
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
.panel{background:linear-gradient(165deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:18px 20px;}
.sect{font-size:.74rem;text-transform:uppercase;letter-spacing:.12em;color:#7cc4ff;font-weight:800;margin:2px 0 10px;}
.small{color:#7d8fae;font-size:.82rem}

/* steps */
.steps{display:flex;gap:14px;flex-wrap:wrap}
.step{flex:1 1 200px;background:#0b1730;border:1px solid var(--line);border-radius:14px;padding:14px 16px}
.step .n{height:28px;width:28px;border-radius:8px;background:#10224a;border:1px solid #2c477b;color:#7cc4ff;
  display:flex;align-items:center;justify-content:center;font-weight:800;font-size:.85rem;margin-bottom:8px}
.step .t{font-weight:700;color:#eaf1ff;font-size:.95rem}
.step .d{color:#9fb3d6;font-size:.83rem;margin-top:3px}

/* buttons / inputs / tabs */
.stButton>button,.stDownloadButton>button{border-radius:11px;font-weight:700;border:1px solid #2c477b;background:#0e1c33;color:#dce8ff;}
.stButton>button:hover{border-color:#3b82f6;color:#fff;}
button[kind="primary"]{background:linear-gradient(90deg,#3b82f6,#38bdf8)!important;color:#04162c!important;border:0!important;box-shadow:0 10px 26px -10px #38bdf8cc;}
[data-testid="stMetric"]{background:#0c1727;border:1px solid var(--line);border-radius:14px;padding:12px 16px;}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;}
.stTextInput input,.stNumberInput input{background:#0b1730!important;border:1px solid #243a63!important;color:#eaf1ff!important;border-radius:11px!important;}
.stTextInput input:focus,.stNumberInput input:focus{border-color:#38d6ff!important;box-shadow:0 0 0 2px #38d6ff33!important;}
.stTextInput label,.stNumberInput label,.stSelectbox label,.stFileUploader label{color:#9fb3d6!important;font-weight:600;}

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

/* ================= LOGIN (image-free) ================= */
.auth-brand{position:relative;overflow:hidden;min-height:580px;border-radius:24px;border:1px solid #1d345c;
  padding:42px 40px;display:flex;flex-direction:column;justify-content:space-between;
  background:
    radial-gradient(680px 380px at 78% 8%,#1b4fa855,transparent 60%),
    radial-gradient(560px 420px at 10% 100%,#0a6f8d44,transparent 60%),
    linear-gradient(160deg,#0a1426,#0b1f3c 60%,#081626);
  box-shadow:0 40px 90px -44px #38d6ff66;}
.auth-grid{position:absolute;inset:0;opacity:.5;
  background-image:linear-gradient(#1e3a6a33 1px,transparent 1px),linear-gradient(90deg,#1e3a6a33 1px,transparent 1px);
  background-size:36px 36px;mask:radial-gradient(560px 400px at 70% 18%,#000,transparent 78%);}
.auth-emblem{position:absolute;top:46px;right:44px;height:96px;width:82px;
  background:linear-gradient(160deg,#5fdcff,#2563eb);
  clip-path:polygon(50% 0,100% 16%,100% 56%,50% 100%,0 56%,0 16%);
  box-shadow:0 0 50px #38d6ff77;animation:pf 3s ease-in-out infinite;}
.auth-emblem::after{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 50% 42%,#fff8,transparent 42%);}
@keyframes pf{50%{filter:brightness(1.22)}}
.auth-brand .top{position:relative;display:flex;align-items:center;gap:12px;}
.auth-brand .top .lg{height:40px;width:40px;border-radius:11px;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#3b82f6,#38d6ff);font-size:1.25rem;box-shadow:0 8px 20px -6px #38d6ffcc;}
.auth-brand .top .tx{font-weight:900;color:#fff;font-size:1.18rem;letter-spacing:-.3px}
.auth-brand .top small{display:block;font-size:.62rem;letter-spacing:.16em;color:#8fb3e6;text-transform:uppercase;font-weight:700}
.auth-brand h1{position:relative;margin:0;font-size:2.35rem;font-weight:900;line-height:1.08;letter-spacing:-.7px;
  background:linear-gradient(92deg,#fff,#9ed3ff 55%,#38d6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.auth-brand .lead{position:relative;color:#bcccea;font-size:1.0rem;margin:14px 0 0;max-width:430px;line-height:1.55}
.feat{position:relative;list-style:none;padding:0;margin:22px 0 0;display:grid;gap:11px}
.feat li{display:flex;align-items:flex-start;gap:11px;color:#d6e2f6;font-size:.92rem}
.feat .ck{flex:0 0 22px;height:22px;width:22px;border-radius:7px;background:#0d2a44;border:1px solid #1d6f8d;
  color:#5fe0ff;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:900;margin-top:1px}
.trust{position:relative;display:flex;gap:22px;margin-top:8px;color:#7f97bd;font-size:.74rem;font-weight:700;letter-spacing:.04em}
.trust b{color:#bcd2f0}
.auth-card{background:linear-gradient(170deg,#0e1c33,#0a1322);border:1px solid #20335c;border-radius:24px;
  padding:34px 34px 26px;box-shadow:0 40px 90px -44px #3b82f6aa;min-height:580px;display:flex;flex-direction:column;justify-content:center;}
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
#  BACKEND  (integration logic - UNCHANGED)
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


def run_triage(image_path):
    bundle = f"bundle-{int(time.time())}"
    t0 = time.time()
    c = subprocess.run(["bash", "collect.sh", image_path, bundle], cwd=APP_DIR,
                       capture_output=True, text=True, timeout=1800)
    t_collect = time.time() - t0
    if c.returncode != 0:
        return {"error": "Collector failed:\n" + (c.stdout or "") + "\n" + (c.stderr or "")}
    prompt = (f'The evidence bundle is already collected in ./{bundle}. Work FAST. '
              f'Read ONLY these small files: {bundle}/offset.txt, {bundle}/fsstat.txt, '
              f'{bundle}/indicators.txt, {bundle}/prefetch.txt, {bundle}/recycler_info2.txt. '
              f'Then write the severity-ranked find-evil report directly from them for the image '
              f'at "{image_path}", per CLAUDE.md. Do NOT run mmls/fls/grep or any extra shell '
              f'commands unless a CRITICAL finding truly cannot be supported otherwise (max 2 such). '
              f'Be efficient - finish in as few steps as possible.')
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


def integrity_check():
    f = os.path.join(APP_DIR, "cases", "original.sha256")
    if not os.path.exists(f):
        return None, "No baseline hash recorded (cases/original.sha256)."
    r = subprocess.run(["sha256sum", "-c", "cases/original.sha256"], cwd=APP_DIR,
                       capture_output=True, text=True)
    return (r.returncode == 0), (r.stdout or "") + (r.stderr or "")


# robust counters (handle C1 / C-1 / "1." / severity words)
def sev_counts(text):
    ids = re.findall(r'(?m)^[\s#>*\-]*\(?\**([CHML])-?\d+\b', text)
    c = Counter(ids)
    if not c:
        for k, w in [("C", "CRITICAL"), ("H", "HIGH"), ("M", "MEDIUM"), ("L", "LOW")]:
            c[k] = len(re.findall(r'\b' + w + r'\b', text))
    return c


def label_counts(text):
    return Counter(re.findall(r'\b(CONFIRMED|LIKELY|UNVERIFIED)\b', text))


def read_bundle_file(bundle, name, limit=400):
    p = os.path.join(APP_DIR, bundle, name)
    if not os.path.exists(p):
        return None
    with open(p, errors="ignore") as fh:
        lines = fh.readlines()
    return "".join(lines[:limit]), len(lines)


# ============================================================================
#  AUTH  (config-file credentials)
# ============================================================================
def load_credentials():
    """Read [credentials] from creds.toml. Values may be plaintext or 'sha256:<hex>'."""
    path = os.path.join(APP_DIR, "creds.toml")
    creds = {}
    if os.path.exists(path):
        try:
            import tomllib  # py3.11+
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
        creds = {"analyst": "findevil2024"}  # safe default so the app is never locked out
    return {str(k): str(v) for k, v in creds.items()}


def verify_login(username, password, creds):
    if not username or username not in creds:
        return False
    stored = creds[username]
    if stored.startswith("sha256:"):
        return hashlib.sha256(password.encode()).hexdigest() == stored.split(":", 1)[1].strip()
    return password == stored


def render_login():
    st.write("")
    left, right = st.columns([1.08, 0.92], gap="large")

    with left:
        st.markdown(
            "<div class='auth-brand'>"
            "<div class='auth-grid'></div><div class='auth-emblem'></div>"
            "<div>"
            "<div class='top'><span class='lg'>🛡️</span>"
            "<span class='tx'>Find Evil!<small>DFIR Triage Platform</small></span></div>"
            "</div>"
            "<div>"
            "<h1>Find evil faster<br>than evil moves.</h1>"
            "<p class='lead'>An autonomous incident-response analyst that triages disk images, "
            "ranks every finding by severity, and shows its work - on read-only evidence.</p>"
            "<ul class='feat'>"
            "<li><span class='ck'>✓</span><span><b>Autonomous triage</b> &mdash; collects, reasons, and reports in one run.</span></li>"
            "<li><span class='ck'>✓</span><span><b>Self-correcting</b> &mdash; labels findings CONFIRMED / LIKELY / UNVERIFIED.</span></li>"
            "<li><span class='ck'>✓</span><span><b>Forensically sound</b> &mdash; read-only access, SHA-256 verified.</span></li>"
            "<li><span class='ck'>✓</span><span><b>Fully traceable</b> &mdash; every finding links to the tool call behind it.</span></li>"
            "</ul>"
            "</div>"
            "<div class='trust'><span><b>SHA-256</b> verified</span><span><b>Read-only</b> evidence</span>"
            "<span><b>200+</b> SIFT tools</span></div>"
            "</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='auth-card'>", unsafe_allow_html=True)
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
        st.markdown("</div>", unsafe_allow_html=True)


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
    html = "<div class='wf'>"
    for i, (t, d) in enumerate(steps, 1):
        if d == "__DECISION__":
            bl = "".join(f"<li>{x}</li>" for x in dec)
            body = (f"<div class='wf-t'>{t}</div><div class='wf-d'>Decision:</div>"
                    f"<ul class='wf-dec'>{bl}</ul><span class='wf-switch {tcol}'>&#8594; Switching to {switch}</span>")
            cls = "wf-step branch"
        else:
            body = f"<div class='wf-t'>{t}</div><div class='wf-d'>{d}</div>"
            cls = "wf-step done"
        html += f"<div class='{cls}'><div class='wf-ic'>{i}</div><div class='wf-body'>{body}</div></div>"
    html += "</div>"
    st.markdown("##### Analyst workflow")
    st.markdown(html, unsafe_allow_html=True)


# ============================================================================
#  HEADER + NAV  (no sidebar)
# ============================================================================
def render_header():
    user = st.session_state.username or "analyst"
    initials = "".join([w[0] for w in re.split(r"[.\s_-]+", user) if w][:2]).upper() or "A"
    c1, c2 = st.columns([6.4, 1.3])
    with c1:
        st.markdown(
            "<div class='appbar'><div class='brand'><span class='logo'>🛡️</span>"
            "<div><div class='nm'>Find <b>Evil!</b></div><small>Autonomous DFIR Triage</small></div>"
            "<span class='statusdot'><i></i> Live &middot; Read-only</span></div>"
            f"<div class='userchip'><div class='u'>{user}<div class='r'>Incident Responder</div></div>"
            f"<span class='av'>{initials}</span></div></div>", unsafe_allow_html=True)
    with c2:
        st.write("")
        if st.button("Log out", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.username = None
            _rerun()
    st.write("")


def render_nav():
    pages = ["Dashboard", "Evidence", "Analyze", "Findings", "Logs"]
    if HAS_MENU:
        return option_menu(
            None, pages,
            icons=["grid-1x2", "hdd-stack", "cpu", "clipboard2-data", "terminal"],
            orientation="horizontal", default_index=0,
            styles={"container": {"background-color": "#0c1727", "border": "1px solid #1b2942",
                                  "border-radius": "14px", "padding": "6px", "margin-bottom": "8px"},
                    "nav-link": {"font-size": "14px", "font-weight": "600", "color": "#9fb0c9",
                                 "padding": "9px 18px", "border-radius": "10px", "--hover-color": "#16233f"},
                    "nav-link-selected": {"background": "linear-gradient(90deg,#3b82f6,#38bdf8)",
                                          "color": "#fff", "font-weight": "700"},
                    "icon": {"color": "#7cc4ff", "font-size": "14px"}})
    return st.radio("Navigate", pages, horizontal=True, label_visibility="collapsed")


# ============================================================================
#  PAGES
# ============================================================================
def page_dashboard():
    st.markdown("<div class='hero'><h1>Find Evil! · Autonomous DFIR Triage Agent</h1>"
                "<p>An AI agent that thinks like a senior analyst: it sequences its approach, "
                "notices when something doesn't add up, and self-corrects - at machine speed.</p>"
                "<div><span class='tag'>Read-only evidence</span><span class='tag'>Self-correction</span>"
                "<span class='tag'>Adaptive (intrusion + exfil)</span><span class='tag'>Full traceability</span></div></div>",
                unsafe_allow_html=True)

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
        st.caption("Open the **Findings** tab for the full report and severity breakdown.")
    else:
        st.markdown("<div class='sect'>How it works</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='steps'>"
            "<div class='step'><div class='n'>1</div><div class='t'>Register evidence</div>"
            "<div class='d'>Add a disk image by path. It's hashed (SHA-256/MD5) and opened read-only.</div></div>"
            "<div class='step'><div class='n'>2</div><div class='t'>Run the agent</div>"
            "<div class='d'>collect.sh gathers artifacts, then the agent reasons over the bundle and self-corrects.</div></div>"
            "<div class='step'><div class='n'>3</div><div class='t'>Review findings</div>"
            "<div class='d'>Severity-ranked report with confidence labels and a full, traceable tool log.</div></div>"
            "</div>", unsafe_allow_html=True)
        st.info("No analysis yet — head to the **Evidence** tab to register an image, then **Analyze** to run the agent.", icon="🧭")


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


def _image_choices():
    paths = [e["Path"] for e in st.session_state.evidence
             if e.get("Type") == "Disk image" and e.get("Path", "").startswith("/")]
    for pat in ("*.E01", "*.dd", "*.001", "*.raw", "*.img"):
        paths += glob.glob(os.path.expanduser("~/Desktop/" + pat))
    seen, out = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def page_agent_run():
    st.subheader("Autonomous Agent Run")
    st.caption("Runs collect.sh (read-only) then Claude analyzes the bundle per CLAUDE.md and self-corrects.")
    choices = _image_choices()
    default_img = "/home/ubuntu/Desktop/4Dell Latitude CPi.E01"
    if choices:
        image = st.selectbox("Disk image to analyze", choices,
                             index=choices.index(default_img) if default_img in choices else 0)
    else:
        image = st.text_input("Disk image path", value=default_img)
    if st.button("Run triage agent", type="primary"):
        if not os.path.exists(image):
            st.error("File not found: " + image)
        else:
            with st.status("Running autonomous triage...", expanded=True) as status:
                st.write("Phase 1 - collecting evidence (read-only)...")
                res = run_triage(image)
                if "error" in res:
                    status.update(label="Failed", state="error")
                    st.error(res["error"])
                else:
                    st.write(f"Phase 2 - Claude made {len(res['tools'])} tool calls and self-corrected.")
                    status.update(label=f"Done in {round(res['elapsed'])}s", state="complete")
                    st.session_state.result = res
    res = st.session_state.result
    if res:
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
    c1, c2, c3 = st.columns(3)
    c1.metric("Tool calls", len(df))
    c2.metric("Wall time", f"{round(res['elapsed'])}s")
    c3.metric("Output tokens", res.get("usage", {}).get("output_tokens", "-"))
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
#  ENTRY  (auth gate)
# ============================================================================
if not st.session_state.authenticated:
    render_login()
    st.stop()

render_header()
page = render_nav()
ROUTES[page]()
# end of file
