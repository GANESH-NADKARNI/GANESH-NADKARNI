#!/usr/bin/env python3
"""
Generates a GitHub-contribution-style SVG heatmap of Codeforces submission
activity for a given handle, using only the Python standard library (no
extra pip installs needed in CI).

Env vars:
  CF_HANDLE   - Codeforces handle to fetch (default: GANESH_NADKARNI)
  OUTPUT_PATH - Where to write the SVG (default: assets/codeforces-heatmap.svg)
  WEEKS       - How many weeks of history to show (default: 53, GitHub-style)
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

CF_HANDLE = os.environ.get("CF_HANDLE", "GANESH_NADKARNI")
OUTPUT_PATH = os.environ.get("OUTPUT_PATH", "assets/codeforces-heatmap.svg")
WEEKS = int(os.environ.get("WEEKS", "53"))

API_URL = f"https://codeforces.com/api/user.status?handle={CF_HANDLE}&from=1&count=10000"

# Brand palette (matches the README: 0D1117 bg / 00D9FF cyan / 7B2FFF purple)
BG_COLOR = "transparent"
EMPTY_FILL = "#161b22"
EMPTY_STROKE = "#30363d"
LEVEL_COLORS = ["#0a2f3d", "#0d4a5e", "#0089b3", "#00c2e6", "#00D9FF"]
TEXT_COLOR = "#8b949e"

CELL_SIZE = 11
CELL_GAP = 3
CELL_STEP = CELL_SIZE + CELL_GAP
LEFT_MARGIN = 28
TOP_MARGIN = 20
MONTH_LABEL_GAP = 16

DAY_LABELS = {1: "Mon", 3: "Wed", 5: "Fri"}  # Monday=0 ... Sunday=6, we use Sun-start grid below
MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def fetch_submissions(handle):
    req = urllib.request.Request(
        API_URL, headers={"User-Agent": "cf-heatmap-generator/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"Failed to fetch Codeforces API: {e}", file=sys.stderr)
        return []

    if data.get("status") != "OK":
        print(f"Codeforces API returned an error: {data.get('comment')}", file=sys.stderr)
        return []

    return data.get("result", [])


def count_submissions_per_day(submissions):
    counts = {}
    for sub in submissions:
        ts = sub.get("creationTimeSeconds")
        if ts is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).date()
        counts[day] = counts.get(day, 0) + 1
    return counts


def level_for_count(count, max_count):
    if count == 0:
        return -1  # empty
    if max_count <= 0:
        return 0
    ratio = count / max_count
    if ratio <= 0.2:
        return 0
    if ratio <= 0.4:
        return 1
    if ratio <= 0.6:
        return 2
    if ratio <= 0.8:
        return 3
    return 4


def build_grid(counts, weeks):
    today = datetime.now(timezone.utc).date()
    # End the grid on the most recent Saturday so the last column is complete-ish
    days_since_sunday = (today.weekday() + 1) % 7  # weekday(): Mon=0..Sun=6 -> convert to Sun=0
    end = today
    start = end - timedelta(days=weeks * 7 - 1)
    # Align start to a Sunday
    start_days_since_sunday = (start.weekday() + 1) % 7
    start = start - timedelta(days=start_days_since_sunday)

    cells = []  # (week_index, day_index(0=Sun..6=Sat), date, count)
    day = start
    week_index = 0
    day_index = 0
    max_count = max(counts.values()) if counts else 0

    while day <= end:
        count = counts.get(day, 0)
        cells.append((week_index, day_index, day, count))
        day_index += 1
        if day_index == 7:
            day_index = 0
            week_index += 1
        day += timedelta(days=1)

    return cells, week_index + (1 if day_index != 0 else 0), max_count


def month_label_positions(cells):
    """Return {week_index: month_name} for the first week each month appears in."""
    seen_months = set()
    labels = {}
    for week_index, day_index, date, _count in cells:
        if day_index == 0:  # only check at start of week to avoid dup labels mid-week
            key = (date.year, date.month)
            if key not in seen_months:
                seen_months.add(key)
                labels[week_index] = MONTH_NAMES[date.month - 1]
    return labels


def render_svg(cells, total_weeks, max_count, handle):
    width = LEFT_MARGIN + total_weeks * CELL_STEP + 10
    height = TOP_MARGIN + MONTH_LABEL_GAP + 7 * CELL_STEP + 30

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="\'Segoe UI\', Helvetica, Arial, sans-serif">'
    )
    if BG_COLOR != "transparent":
        parts.append(f'<rect width="{width}" height="{height}" fill="{BG_COLOR}"/>')

    # Month labels
    for week_index, label in month_label_positions(cells).items():
        x = LEFT_MARGIN + week_index * CELL_STEP
        y = TOP_MARGIN
        parts.append(
            f'<text x="{x}" y="{y}" font-size="10" fill="{TEXT_COLOR}">{label}</text>'
        )

    # Day-of-week labels (Mon/Wed/Fri), grid rows are Sun=0..Sat=6
    day_row_labels = {1: "Mon", 3: "Wed", 5: "Fri"}
    for row, label in day_row_labels.items():
        x = 0
        y = TOP_MARGIN + MONTH_LABEL_GAP + row * CELL_STEP + CELL_SIZE
        parts.append(
            f'<text x="{x}" y="{y}" font-size="9" fill="{TEXT_COLOR}">{label}</text>'
        )

    # Cells
    for week_index, day_index, date, count in cells:
        x = LEFT_MARGIN + week_index * CELL_STEP
        y = TOP_MARGIN + MONTH_LABEL_GAP + day_index * CELL_STEP
        level = level_for_count(count, max_count)
        if level == -1:
            fill = EMPTY_FILL
            stroke = EMPTY_STROKE
        else:
            fill = LEVEL_COLORS[level]
            stroke = LEVEL_COLORS[level]
        title = f"{date.isoformat()}: {count} submission{'s' if count != 1 else ''}"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" ry="2" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1">'
            f'<title>{title}</title></rect>'
        )

    # Legend
    legend_y = height - 14
    legend_x = LEFT_MARGIN
    parts.append(
        f'<text x="{legend_x}" y="{legend_y + 9}" font-size="9" fill="{TEXT_COLOR}">Less</text>'
    )
    lx = legend_x + 32
    parts.append(
        f'<rect x="{lx}" y="{legend_y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" ry="2" '
        f'fill="{EMPTY_FILL}" stroke="{EMPTY_STROKE}" stroke-width="1"/>'
    )
    lx += CELL_STEP
    for color in LEVEL_COLORS:
        parts.append(
            f'<rect x="{lx}" y="{legend_y}" width="{CELL_SIZE}" height="{CELL_SIZE}" rx="2" ry="2" '
            f'fill="{color}" stroke="{color}" stroke-width="1"/>'
        )
        lx += CELL_STEP
    parts.append(
        f'<text x="{lx + 4}" y="{legend_y + 9}" font-size="9" fill="{TEXT_COLOR}">More</text>'
    )

    total_subs = sum(c for *_rest, c in cells)
    parts.append(
        f'<text x="{width - 10}" y="{TOP_MARGIN}" font-size="10" fill="{TEXT_COLOR}" '
        f'text-anchor="end">{handle} · {total_subs} submissions (last {len(cells)//7} weeks)</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    submissions = fetch_submissions(CF_HANDLE)
    counts = count_submissions_per_day(submissions)
    cells, total_weeks, max_count = build_grid(counts, WEEKS)
    svg = render_svg(cells, total_weeks, max_count, CF_HANDLE)

    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"Wrote {OUTPUT_PATH} ({len(submissions)} submissions fetched, {len(counts)} active days)")


if __name__ == "__main__":
    main()