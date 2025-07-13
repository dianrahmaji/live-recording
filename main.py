import requests
import time
import subprocess
import os
import sys
import re
import signal
from collections import defaultdict
from datetime import datetime

ids = [
    "61d9d168-a875-498d-97e3-7126f2c7c208",  # Slovia Official
    # "331b1f61-7819-4881-b6c5-a8554670ea87",  # Carnelian Ofc - Testing
    # "2cee7c32-e03b-41e5-b79d-f65d3207b12c",  # ORIHIME Project - Testing
    # "f2ab983d-c324-4046-acf0-a03d1e68755d",  # Ametta Official - Testing
    # "5fc0bf74-e35c-4643-8400-8ff9ca5bf882",  # Aurora Dream - Testing
]

url = "https://api.idn.app/graphql"
query = """
    query($page: Int) {
        getLivestreams(category: "all", page: $page) {
            title
            playback_url
            status
            scheduled_at
            creator {
                uuid
                name
            }
        }
    }
"""


def get_livestreams():
    page = 1
    livestreams = []

    while True:
        variables = {
            "page": page
        }

        payload = {
            "query": query,
            "variables": variables
        }

        response = requests.post(url, json=payload)
        data = response.json()

        items = data["data"]["getLivestreams"]

        if not items:
            break

        livestreams.extend(items)
        page += 1

    return livestreams


def format_time_diff(scheduled_at):
    try:
        dt = datetime.fromisoformat(scheduled_at)
        now = datetime.now(dt.tzinfo)
        delta = dt - now
        total_minutes = int(delta.total_seconds() // 60)

        if total_minutes > 0:
            days = total_minutes // (60 * 24)
            hours = (total_minutes % (60 * 24)) // 60
            minutes = total_minutes % 60

            parts = []
            if days:
                parts.append(f"{days}d")
            if hours:
                parts.append(f"{hours}h")
            if minutes:
                parts.append(f"{minutes}m")

            return f"in {' '.join(parts)}"
        else:
            return "starting soon"
    except Exception:
        return "unknown time"


def get_ongoing_livestreams():
    livestreams = get_livestreams()

    filtered = []
    live = []
    scheduled = defaultdict(list)

    for item in livestreams:
        creator_id = item["creator"]["uuid"]
        if creator_id in ids:
            filtered.append(item)

    if not filtered:
        print("No interested livestreams!")
        return

    for item in filtered:
        creator = item["creator"]["name"]
        title = item["title"]
        status = item["status"]
        playback_url = item["playback_url"]
        scheduled_at = item["scheduled_at"]

        if status == "scheduled":
            scheduled[creator].append({
                "title": title,
                "scheduled_at": scheduled_at
            })
        elif status == "live":
            live.append({
                "creator": creator,
                "title": title,
                "playback_url": playback_url
            })

    for creator, streams in scheduled.items():
        print(f"{creator} has scheduled livestreams:")

        for stream in streams:
            time_msg = format_time_diff(stream["scheduled_at"])
            print(f" - {stream['title']} ({time_msg})")

        print()

    for stream in live:
        print(f"{stream['creator']} is live now: {stream['title']}\n")

    return live


def sanitize_str(str):
    s = re.sub(
        r"[\U0001F600-\U0001F64F"
        r"\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0"
        r"\U000024C2-\U0001F251"
        r"]+", '', str, flags=re.UNICODE)

    s = re.sub(r'[^\w\-_. ]', '_', s)
    return s.strip().replace(' ', '_')


def record_livestreams():
    livestreams = get_ongoing_livestreams()
    processes = []

    os.makedirs("recordings", exist_ok=True)

    for stream in livestreams:
        creator = sanitize_str(stream["creator"])
        raw_title = stream["title"]
        title = sanitize_str(raw_title)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        filename = f"{creator}_{title}_{timestamp}.mp4"
        path = os.path.join("recordings", filename)
        cmd = [
            "ffmpeg",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",
            "-i", stream["playback_url"],
            "-c:v", "libx264",
            "-c:a", "aac",
            "-movflags", "+frag_keyframe+empty_moov",
            "-f", "mp4",
            "-y", path
        ]

        print(f"Recording {creator} - {raw_title} → {path}\n")

        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes.append((proc, path, creator, title, raw_title))

    i = 0
    spinners = ['|', '/', '-', '\\']

    try:
        while any(proc.poll() is None for proc, *_ in processes):
            for proc, path, creator, title, raw_title in processes:
                name = f"{creator} - {raw_title}"
                spinner = f"{spinners[i % len(spinners)]}"

                sys.stdout.write("\r")

                if proc.poll() is None:
                    if os.path.exists(path):
                        size = f"{os.path.getsize(path) / (1024 * 1024):.2f}MB"
                        sys.stdout.write(f"Recording {name} {
                                         spinner} ({size})")
                    else:
                        sys.stdout.write(f"Recording {name} starting")
                else:
                    sys.stdout.write(f"Recording {name} finished")

                sys.stdout.flush()

                i += 1
                time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nTerminating...")
        for proc, *_ in processes:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)

        for proc, *_ in processes:
            try:
                proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


record_livestreams()
