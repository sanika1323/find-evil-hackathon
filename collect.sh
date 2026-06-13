#!/usr/bin/env bash
# Generalized read-only DFIR collector - works for INTRUSION and EXFILTRATION.
# Exfil logic is GENERIC: attachment + recipient outside the auto-detected home domain.
set -uo pipefail
IMG="$1"; OUT="${2:-bundle}"
mkdir -p "$OUT"

echo "[*] partitions (mmls)"
mmls "$IMG" > "$OUT/partitions.txt" 2>&1
OFF=$(awk '/NTFS|FAT|exFAT|0x07|0x83|Linux/{print $3; exit}' "$OUT/partitions.txt" | sed 's/^0*//')
OFF="${OFF:-0}"; echo "$OFF" > "$OUT/offset.txt"
echo "[*] offset = $OFF"

echo "[*] fsstat";       fsstat -o "$OFF" "$IMG" > "$OUT/fsstat.txt" 2>&1
echo "[*] file listing"; fls -r -o "$OFF" "$IMG" > "$OUT/files.txt" 2>&1
echo "[*] timeline";     fls -r -m C: -o "$OFF" "$IMG" > "$OUT/body.txt" 2>&1
mactime -y -b "$OUT/body.txt" -d > "$OUT/timeline.csv" 2>&1

grep -iaE '\b(netcat|nc\.exe|pwdump[0-9]?|samdump|cain|abel|john-?[0-9]|l0pht|nmapnt|nmap|nbtscan|enum\.exe|brutus|netbus|sub7|winvnc|vncviewer|psexec|mimikatz|lsadump|getadmin|sechole|elsave|ettercap|ophcrack)\b' \
  "$OUT/files.txt" > "$OUT/indicators.txt" 2>/dev/null
echo "[*] prefetch"
grep -iaE '\.pf[: ]' "$OUT/files.txt" > "$OUT/prefetch.txt" 2>&1

grep -iaE '\.(xls|xlsx|doc|docx|ppt|pptx|pdf|csv|rtf|ods)\b' "$OUT/files.txt" > "$OUT/documents.txt" 2>&1
grep -iaE '\b(salary|salaries|plan|budget|confidential|payroll|finance|funding|invoice|ssn)\b' "$OUT/files.txt" >> "$OUT/documents.txt" 2>&1

: > "$OUT/email.txt"
grep -iaE '\.(pst|ost|dbx|mbox|eml|msg)\b|outlook|inbox|sent items' "$OUT/files.txt" >> "$OUT/email.txt" 2>&1
MAILDIR="$OUT/mail"; rm -rf "$MAILDIR"; mkdir -p "$MAILDIR"
for INO in $(grep -iaE '\.(pst|ost)\b' "$OUT/files.txt" | grep -oE '[0-9]+-[0-9]+-[0-9]+' | cut -d- -f1 | sort -u | head -6); do
  TMP="$OUT/.m_$INO"; icat -o "$OFF" "$IMG" "$INO" > "$TMP" 2>/dev/null
  mkdir -p "$MAILDIR/$INO"
  command -v readpst >/dev/null 2>&1 && readpst -e -q -D -o "$MAILDIR/$INO" "$TMP" >/dev/null 2>&1
  rm -f "$TMP"
done
if [ -z "$(find "$MAILDIR" -type f 2>/dev/null)" ]; then
  for INO in $(grep -iaE '\.(pst|ost|dbx|mbox)\b' "$OUT/files.txt" | grep -oE '[0-9]+-[0-9]+-[0-9]+' | cut -d- -f1 | sort -u | head -4); do
    icat -o "$OFF" "$IMG" "$INO" 2>/dev/null | strings | grep -iaE '@|subject:|filename=|attach' | head -500 >> "$OUT/email.txt"
  done
fi

HOME_DOMAIN=$(grep -rhoiaE '@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$MAILDIR" 2>/dev/null | tr '[:upper:]' '[:lower:]' | sort | uniq -c | sort -rn | head -1 | grep -oiE '@[A-Za-z0-9.-]+')
[ -z "$HOME_DOMAIN" ] && HOME_DOMAIN="@__none__"
echo "AUTO-DETECTED HOME/ORG DOMAIN: $HOME_DOMAIN" > "$OUT/exfil_candidates.txt"

if find "$MAILDIR" -type f >/dev/null 2>&1; then
  find "$MAILDIR" -type f 2>/dev/null | while read -r f; do
    HASATT=$(grep -iE 'filename=|Content-Disposition:[[:space:]]*attachment' "$f" 2>/dev/null | head -1)
    [ -z "$HASATT" ] && continue
    EXT=$(sed -n '1,80p' "$f" 2>/dev/null | grep -ioE '@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' | tr '[:upper:]' '[:lower:]' | grep -ivF "$HOME_DOMAIN" | head -1)
    [ -z "$EXT" ] && continue
    {
      echo ""; echo "### EXFIL CANDIDATE - attachment + EXTERNAL domain ($EXT)"
      sed -n '1,80p' "$f" 2>/dev/null | grep -iE '^(From|To|Cc|Subject|Date):' | head -8
      grep -iE 'filename=' "$f" 2>/dev/null | head -3
    } >> "$OUT/exfil_candidates.txt"
  done
fi

grep -iaE 'index\.dat|history|temporary internet|cache|cookies|hotmail|gmail|yahoo|webmail|outlook\.com|squirrelmail' \
  "$OUT/files.txt" > "$OUT/webmail.txt" 2>&1

INODE=$(grep -ia 'INFO2' "$OUT/files.txt" | head -1 | grep -oE '[0-9]+-[0-9]+-[0-9]+' | head -1 | cut -d- -f1)
[ -n "${INODE:-}" ] && icat -o "$OFF" "$IMG" "$INODE" 2>/dev/null | strings > "$OUT/recycler_info2.txt"

{
  echo ""; echo "## EXFILTRATION CANDIDATES (auto: attachment to/from external domain)"
  head -160 "$OUT/exfil_candidates.txt" 2>/dev/null
  echo ""; echo "## DATA-EXFIL LEADS - sensitive documents on disk"; head -40 "$OUT/documents.txt" 2>/dev/null
  echo ""; echo "## DATA-EXFIL LEADS - email domains seen (count desc; top = internal)"
  grep -rhoiaE '@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$MAILDIR" 2>/dev/null | tr '[:upper:]' '[:lower:]' | sort | uniq -c | sort -rn | head -40
  echo ""; echo "## DATA-EXFIL LEADS - attachments seen in mail"
  grep -rhiaE 'filename=' "$MAILDIR" 2>/dev/null | sort -u | head -40
  echo ""; echo "## DATA-EXFIL LEADS - webmail/browser artifacts"; head -30 "$OUT/webmail.txt" 2>/dev/null
} >> "$OUT/indicators.txt"

echo "[*] done -> $OUT/"; ls -la "$OUT/"