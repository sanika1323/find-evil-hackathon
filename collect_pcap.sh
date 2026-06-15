#!/usr/bin/env bash
# collect_pcap.sh — read-only network-capture collector for "Find Evil!"
# Usage: collect_pcap.sh <capture.pcap|pcapng|cap> <bundle_dir>
set -u
PCAP="${1:?usage: collect_pcap.sh <pcap> <bundle_dir>}"
BUNDLE="${2:-bundle-$(date +%s)}"
mkdir -p "$BUNDLE"
for f in capinfos protocol_hierarchy endpoints conversations dns \
         http_requests smtp credentials dhcp_hostnames emails indicators manifest; do
    : > "$BUNDLE/$f.txt"
done
if ! command -v tshark >/dev/null 2>&1; then
    {
        echo "# tshark NOT FOUND. Install:  sudo apt-get install -y tshark"
        echo "# Strings fallback:"
        strings -n 6 "$PCAP" 2>/dev/null \
          | grep -aiE "password|passwd|pwd=|login|user=|MAIL FROM|RCPT TO|Subject:|authorization|GET |POST |Host:" \
          | sort -u | head -150
    } > "$BUNDLE/indicators.txt"
    ls -la "$BUNDLE" > "$BUNDLE/manifest.txt" 2>/dev/null
    echo "collect_pcap.sh: tshark missing — wrote strings fallback"; exit 0
fi
TS="tshark -n -r $PCAP"
if command -v capinfos >/dev/null 2>&1; then
    capinfos "$PCAP" 2>/dev/null > "$BUNDLE/capinfos.txt"
else
    $TS -q -z io,stat,0 2>/dev/null > "$BUNDLE/capinfos.txt"
fi
$TS -q -z io,phs 2>/dev/null > "$BUNDLE/protocol_hierarchy.txt"
{ echo "== IP endpoints =="; $TS -q -z endpoints,ip 2>/dev/null; \
  echo; echo "== Ethernet (MAC) endpoints =="; $TS -q -z endpoints,eth 2>/dev/null; } > "$BUNDLE/endpoints.txt"
{ echo "== IP conversations =="; $TS -q -z conv,ip 2>/dev/null; \
  echo; echo "== TCP conversations =="; $TS -q -z conv,tcp 2>/dev/null | head -120; } > "$BUNDLE/conversations.txt"
$TS -Y "dns.flags.response==0" -T fields -e frame.time_relative -e ip.src -e dns.qry.name 2>/dev/null \
    | sort -u | head -300 > "$BUNDLE/dns.txt"
$TS -Y "http.request" -T fields -e frame.time_relative -e ip.src -e http.host \
    -e http.request.method -e http.request.uri -e http.user_agent 2>/dev/null | head -400 > "$BUNDLE/http_requests.txt"
$TS -Y "smtp" -T fields -e frame.time_relative -e ip.src -e ip.dst \
    -e smtp.req.command -e smtp.req.parameter -e smtp.data.fragment 2>/dev/null | head -400 > "$BUNDLE/smtp.txt"
{ echo "== DHCP hostnames =="; $TS -Y "dhcp" -T fields -e dhcp.ip.client -e dhcp.option.hostname 2>/dev/null | sort -u | head -60; \
  echo; echo "== NetBIOS names =="; $TS -Y "nbns" -T fields -e nbns.name 2>/dev/null | sort -u | head -60; } > "$BUNDLE/dhcp_hostnames.txt"
{ echo "== tshark credentials tap =="; $TS -q -z credentials 2>/dev/null; \
  echo; echo "== HTTP POST form fields =="; $TS -Y 'http.request.method=="POST"' -T fields -e http.host -e http.request.uri -e urlencoded-form.key -e urlencoded-form.value 2>/dev/null | head -200; \
  echo; echo "== HTTP Authorization headers =="; $TS -Y "http.authorization" -T fields -e http.host -e http.authorization 2>/dev/null | head -100; \
  echo; echo "== FTP credentials =="; $TS -Y 'ftp.request.command=="USER" || ftp.request.command=="PASS"' -T fields -e ip.dst -e ftp.request.command -e ftp.request.arg 2>/dev/null | head -100; } > "$BUNDLE/credentials.txt"
$TS -T fields -e text 2>/dev/null | grep -aoE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" | sort -u | head -200 > "$BUNDLE/emails.txt"
{ echo "# Network indicators (best-effort) — capture: $PCAP"; echo; \
  echo "## Top IP talkers"; sed -n '1,12p' "$BUNDLE/endpoints.txt"; echo; \
  echo "## Interesting hosts / webmail / uploads"; \
  grep -aiE "mail|smtp|webmail|gmail|yahoo|hotmail|outlook|login|upload|ftp|paste|drive" "$BUNDLE/http_requests.txt" "$BUNDLE/dns.txt" 2>/dev/null | head -60; echo; \
  echo "## Credentials present?"; grep -aiE "password|pass|user|authorization|USER|PASS" "$BUNDLE/credentials.txt" 2>/dev/null | head -40; echo; \
  echo "## Keyword sweep over raw bytes"; \
  strings -n 6 "$PCAP" 2>/dev/null | grep -aiE "password|passwd|pwd=|MAIL FROM|RCPT TO|Subject:|bomb|threat|kill|attack|confidential|secret" | sort -u | head -120; } > "$BUNDLE/indicators.txt"
ls -la "$BUNDLE" > "$BUNDLE/manifest.txt" 2>/dev/null
echo "collect_pcap.sh: wrote network bundle -> $BUNDLE"
exit 0