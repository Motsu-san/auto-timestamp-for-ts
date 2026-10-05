"""Record PC power/session events (sleep, lid close, screen lock, shutdown, ...) of finished days
into auto_timestamp_inout.log.

Usage:
  python record_pc_events.py               # record every finished day not yet recorded (up to yesterday)
  python record_pc_events.py -D 2026-10-02 # record the given day (does not update the recorded marker)
  pythonw record_pc_events.py --lock       # append the current time as a screen-lock event (for the lock trigger task)

Sleep / lid close / shutdown are read from the Windows System event log afterwards.
Screen lock is not readable from the event log without admin rights (Security log), so it is
recorded at lock time by a scheduled task (trigger: "On workstation lock") calling --lock.
"""

import argparse
import datetime
import locale
import subprocess
import xml.etree.ElementTree as ET
from logging import StreamHandler, basicConfig, getLogger, handlers
from pathlib import Path

LOG_DIR = Path(__file__).parent / "log"
LOG_FILE_PATH = str(LOG_DIR / "auto_timestamp_inout.log")
PATH_LOCK_EVENTS = LOG_DIR / "session_lock_events.log"
PATH_LAST_RECORDED = LOG_DIR / "PC_EVENTS_RECORDED"
MAX_BACKLOG_DAYS = 31

EVENT_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

# Kernel-Power 506/507 "Reason" (POWER_MONITOR_REQUEST_REASON)
MODERN_STANDBY_REASONS = {
    1: "power button",
    7: "sleep requested",
    11: "screen off request",
    12: "idle timeout",
    14: "sleep button",
    15: "lid closed",
    20: "sleep/hibernate transition",
    21: "system idle",
    23: "thermal standby",
}
# Kernel-Power 42 "TargetState" (SYSTEM_POWER_STATE)
SLEEP_TARGET_STATES = {2: "SLEEP (S1)", 3: "SLEEP (S2)", 4: "SLEEP (S3)", 5: "HIBERNATE"}

logger = getLogger(__name__)


def record_lock():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(PATH_LOCK_EVENTS, "a", encoding="utf-8") as f:
        f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\tLOCK\n")


def _to_utc_str(dt_local):
    return dt_local.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_utc(time_str):
    """'2026-10-02T01:24:43.9225619Z' (UTC) -> naive local datetime"""
    base, _, frac = time_str.rstrip("Z").partition(".")
    time_utc = datetime.datetime.fromisoformat(f"{base}.{frac[:6].ljust(6, '0')}+00:00")
    return time_utc.astimezone().replace(tzinfo=None)


def _decode(output):
    # wevtutil writes in the ANSI code page (cp932 on Japanese Windows) unless UTF-8 is the system code page
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError:
        return output.decode(locale.getpreferredencoding(False), errors="replace")


def query_system_events(start_local, end_local):
    """Return power-related System log events in [start_local, end_local) as a list of dicts."""
    query = (
        "*[System[("
        "(Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=42 or EventID=506 or EventID=507))"
        " or (Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and EventID=1)"
        " or (Provider[@Name='Microsoft-Windows-Kernel-General'] and (EventID=12 or EventID=13))"
        " or (Provider[@Name='User32'] and EventID=1074)"
        " or (Provider[@Name='EventLog'] and EventID=6008)"
        f") and TimeCreated[@SystemTime>='{_to_utc_str(start_local)}' and @SystemTime<'{_to_utc_str(end_local)}']]]"
    )
    result = subprocess.run(
        ["wevtutil", "qe", "System", f"/q:{query}", "/f:xml", "/e:Events"],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        raise RuntimeError(f"wevtutil failed: {_decode(result.stderr).strip()}")

    events = []
    for ev in ET.fromstring(_decode(result.stdout)).findall("e:Event", EVENT_NS):
        system = ev.find("e:System", EVENT_NS)
        # unnamed <Data> (e.g. EventLog 6008) are keyed by position: "#0", "#1", ...
        data = {
            d.get("Name") or f"#{n}": (d.text or "") for n, d in enumerate(ev.findall("e:EventData/e:Data", EVENT_NS))
        }
        events.append(
            {
                "provider": system.find("e:Provider", EVENT_NS).get("Name"),
                "id": int(system.find("e:EventID", EVENT_NS).text),
                "record_id": int(system.find("e:EventRecordID", EVENT_NS).text),
                "time": _parse_utc(system.find("e:TimeCreated", EVENT_NS).get("SystemTime")),
                "data": data,
            }
        )
    events.sort(key=lambda e: e["record_id"])
    return events


def _clean(text):
    # U+200E (left-to-right mark) in localized dates becomes "?" in cp932
    return text.replace("‎", "").replace("?", "").strip()


def _is(e, provider, event_id):
    return e["provider"] == provider and e["id"] == event_id


def describe_modern_standby(events):
    """Return [(datetime, description)] of Modern Standby sessions (Kernel-Power 506 enter / 507 exit).

    During a long standby Windows emits 507 and a new 506 at the same moment as a checkpoint
    (ExitLatencyInUs=0, IsCsSessionInProgressOnExit=true); such segments are joined into one session.
    """
    enters = [e for e in events if _is(e, "Microsoft-Windows-Kernel-Power", 506)]
    exits = {e["data"].get("ScenarioInstanceIdV2"): e for e in events if _is(e, "Microsoft-Windows-Kernel-Power", 507)}

    def next_enter(exit_ev):
        for e in enters:
            if e["record_id"] > exit_ev["record_id"] and abs((e["time"] - exit_ev["time"]).total_seconds()) < 1:
                return e
        return None

    continued = set()
    items = []
    for enter in enters:
        if enter["record_id"] in continued:
            continue
        reason_nos = [int(enter["data"].get("Reason", "-1"))]
        exit_ev = exits.get(enter["data"].get("ScenarioInstanceIdV2"))
        slept = False
        while exit_ev is not None:
            slept |= exit_ev["data"].get("SleepEntered") == "true"
            if not (exit_ev["data"].get("ExitLatencyInUs") == "0" and exit_ev["data"].get("IsCsSessionInProgressOnExit") == "true"):
                break
            nxt = next_enter(exit_ev)
            if nxt is None:
                break
            continued.add(nxt["record_id"])
            reason_nos.append(int(nxt["data"].get("Reason", "-1")))
            exit_ev = exits.get(nxt["data"].get("ScenarioInstanceIdV2"))

        known = [MODERN_STANDBY_REASONS[n] for n in reason_nos if n in MODERN_STANDBY_REASONS]
        reason = ", ".join(dict.fromkeys(known)) or f"reason={reason_nos[0]}"
        if exit_ev is None:
            items.append((enter["time"], f"SCREEN_OFF/SLEEP ({reason}) -> not resumed yet"))
            continue
        if not slept and (exit_ev["time"] - enter["time"]).total_seconds() < 2:
            continue  # momentary screen-off just before another transition
        kind = "SLEEP" if slept else "SCREEN_OFF"
        items.append((enter["time"], f"{kind} ({reason}) -> resumed {exit_ev['time']:%m/%d %H:%M:%S}"))
    return items


def describe_events(day, events):
    """Return [(datetime, description)] for events that occurred on the given day."""
    items = [(t, desc) for t, desc in describe_modern_standby(events) if t.date() == day]
    for e in events:
        p, i, d = e["provider"], e["id"], e["data"]
        if p == "Microsoft-Windows-Power-Troubleshooter" and i == 1:
            # TimeCreated is not reliable after hibernate, use WakeTime instead
            wake_time = _parse_utc(d["WakeTime"]) if d.get("WakeTime") else e["time"]
            if wake_time.date() == day:
                sleep_time = _parse_utc(d["SleepTime"]) if d.get("SleepTime") else None
                since = f", since {sleep_time:%m/%d %H:%M:%S}" if sleep_time else ""
                items.append((wake_time, f"RESUME (from {SLEEP_TARGET_STATES.get(int(d.get('TargetState', '0')), 'sleep')}{since})"))
            continue
        if e["time"].date() != day:
            continue
        if p == "Microsoft-Windows-Kernel-Power" and i == 42:
            state = SLEEP_TARGET_STATES.get(int(d.get("TargetState", "0")), "SLEEP")
            items.append((e["time"], state))
        elif p == "Microsoft-Windows-Kernel-General" and i == 13:
            items.append((e["time"], "SHUTDOWN"))
        elif p == "Microsoft-Windows-Kernel-General" and i == 12:
            items.append((e["time"], "BOOT"))
        elif p == "User32" and i == 1074:
            process = _clean(d.get("param1", "")).split(" (")[0].split("\\")[-1]
            items.append(
                (e["time"], f"SHUTDOWN_REQUEST (type={_clean(d.get('param5', ''))}, by={process}, reason={_clean(d.get('param3', ''))})")
            )
        elif p == "EventLog" and i == 6008:
            items.append(
                (e["time"], f"UNEXPECTED_SHUTDOWN detected (previous shutdown at {_clean(d.get('#1', ''))} {_clean(d.get('#0', ''))})")
            )
    return items


def read_lock_events(day):
    if not PATH_LOCK_EVENTS.exists():
        return []
    items = []
    for line in PATH_LOCK_EVENTS.read_text(encoding="utf-8").splitlines():
        time_str, _, kind = line.partition("\t")
        try:
            t = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if t.date() == day:
            items.append((t, kind or "LOCK"))
    return items


def prune_lock_events(last_recorded_day):
    if not PATH_LOCK_EVENTS.exists():
        return
    kept = [
        line
        for line in PATH_LOCK_EVENTS.read_text(encoding="utf-8").splitlines()
        if line[:10] > last_recorded_day.isoformat()
    ]
    PATH_LOCK_EVENTS.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")


def record_days(days):
    # query a few days before (sleep sessions continuing from earlier days) and until now
    # (resumes on later days of sleeps started on the recorded days)
    start = datetime.datetime.combine(days[0] - datetime.timedelta(days=7), datetime.time()).astimezone()
    events = query_system_events(start, datetime.datetime.now().astimezone())
    for day in days:
        logger.info("=== PC EVENTS === " + day.strftime("%Y/%m/%d"))
        items = sorted(describe_events(day, events) + read_lock_events(day), key=lambda x: x[0])
        if not items:
            logger.info("  (no events)")
        for t, desc in items:
            logger.info(f"  {t:%H:%M:%S} {desc}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", action="store_true", help="append the current time as a screen-lock event")
    parser.add_argument("-D", "--date", help="record events of the given day (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.lock:
        record_lock()
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rotatingfilehandler = handlers.RotatingFileHandler(
        LOG_FILE_PATH,
        encoding="utf-8",
        maxBytes=100 * 1024,
        backupCount=20,
    )
    basicConfig(handlers=[StreamHandler(), rotatingfilehandler])
    logger.setLevel("INFO")

    if args.date:
        record_days([datetime.date.fromisoformat(args.date)])
        return

    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    try:
        last_recorded = datetime.date.fromisoformat(PATH_LAST_RECORDED.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        last_recorded = yesterday - datetime.timedelta(days=1)
    first = max(last_recorded + datetime.timedelta(days=1), yesterday - datetime.timedelta(days=MAX_BACKLOG_DAYS - 1))
    if first > yesterday:
        return

    days = [first + datetime.timedelta(days=n) for n in range((yesterday - first).days + 1)]
    record_days(days)
    PATH_LAST_RECORDED.write_text(yesterday.isoformat(), encoding="utf-8")
    prune_lock_events(yesterday)


if __name__ == "__main__":
    main()
