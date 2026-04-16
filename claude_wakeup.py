# claude_wakeup.py
#
# Resets the Claude CLI daily usage window.
# Waits until a configurable time (default: 6:00 AM), then sends a wake-up
# message via the Claude CLI, which starts a new 5-hour usage window.
#
# Usage:
#   python claude_wakeup.py              # triggers at 6:00 AM (default)
#   python claude_wakeup.py --time 07:30 # triggers at 7:30 AM
#
# Background execution:
#   python claude_wakeup.py &                            # background, terminal must stay open
#   nohup python claude_wakeup.py > wakeup.log 2>&1 &   # survives terminal close

import argparse
import subprocess
import time
from datetime import datetime, timedelta


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with a ``time`` attribute (str, HH:MM format).
    """
    parser = argparse.ArgumentParser(
        description="Reset the Claude CLI daily usage window at a scheduled time."
    )
    parser.add_argument(
        "--time",
        default="06:00",
        metavar="HH:MM",
        help="Target wake-up time in 24h format (default: 06:00)",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: wait until the scheduled time, then invoke Claude CLI."""
    args = parse_args()

    try:
        target_time = datetime.strptime(args.time, "%H:%M").time()
    except ValueError:
        print(f"❌ Invalid time format '{args.time}'. Use HH:MM (e.g. 06:00 or 07:30).")
        raise SystemExit(1)

    now = datetime.now()
    target = now.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)

    wait = (target - now).total_seconds()
    print(
        f"⏳ Waking up at {target.strftime('%H:%M')} "
        f"({int(wait // 3600)}h{int(wait % 3600 // 60)}min remaining)"
    )
    time.sleep(wait)

    print(f"🔔 {target.strftime('%H:%M')}! Starting Claude...")
    subprocess.run(["claude", "-p", "Good morning Claude, time to wake up!"])
    print("✅ Done! 5-hour window started.")


if __name__ == "__main__":
    main()
