"""
Core logic: detect silent sections in a video and cut them out.

Approach:
1. Run ffmpeg's silencedetect filter on the audio track to find silence_start/silence_end pairs.
2. Turn those into "keep" segments (the complement), padding each speech segment
   slightly so words aren't clipped, and merging segments that end up too short
   or too close together.
3. Re-encode the video in one pass using a select/aselect filter graph that keeps
   only the chosen time ranges.
"""

import re
import subprocess


class JobCancelled(Exception):
    """Raised when a caller-supplied cancel_event fires while ffmpeg is running."""


def _run(cmd, cancel_event=None, poll_interval=0.3):
    """
    Runs cmd via Popen, polling for completion so cancel_event can interrupt it
    mid-flight (subprocess.run/check_output block uninterruptibly until exit).
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=poll_interval)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise JobCancelled()


def get_duration(path: str, cancel_event=None) -> float:
    returncode, stdout, stderr = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        cancel_event=cancel_event,
    )
    if returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{stderr[-3000:]}")
    return float(stdout.strip())


def detect_silence(path: str, silence_db: float, min_silence_duration: float, cancel_event=None):
    """Returns list of (start, end) tuples for silent sections."""
    cmd = [
        "ffmpeg", "-i", path,
        "-af", f"silencedetect=noise={silence_db}dB:d={min_silence_duration}",
        "-f", "null", "-",
    ]
    _, _, log = _run(cmd, cancel_event=cancel_event)

    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", log)]

    # silence_end lines look like "silence_end: 12.34 | silence_duration: 3.1"
    # the regex above already only grabs the first number, which is what we want.

    silences = []
    for i, s in enumerate(starts):
        if i < len(ends):
            silences.append((s, ends[i]))
        else:
            # silence runs to end of file (no matching silence_end logged)
            silences.append((s, None))
    return silences


def compute_keep_segments(duration, silences, margin_before, margin_after,
                           min_keep_duration, merge_gap=0.0):
    """
    Turn silence intervals into the speech ("keep") intervals that remain
    after cutting, applying asymmetric margins and dropping/merging tiny
    fragments.

    margin_after:  how much of a trailing silence is kept right after a
                   speech segment ends (buffer so the cut doesn't feel abrupt
                   mid-breath).
    margin_before: how much of a leading silence is kept right before the
                   *next* speech segment starts (buffer coming out of a cut).
    merge_gap:     keep segments separated by a gap shorter than this get
                   merged into one, avoiding rapid-fire micro-cuts. 0 disables
                   merging beyond exact overlaps.
    """
    # Clamp silence intervals, resolve open-ended last silence to file duration
    resolved = []
    for s, e in silences:
        e = duration if e is None else e
        s = max(0.0, s)
        e = min(duration, e)
        if e > s:
            resolved.append((s, e))

    # Build keep segments as the complement of silence, adding the margins
    # back in (i.e. shrink each silence window on each side so we keep a
    # small buffer of breathing room around speech).
    keep = []
    cursor = 0.0
    for s, e in resolved:
        seg_start = cursor
        seg_end = min(duration, s + margin_after)
        if seg_end > seg_start:
            keep.append((seg_start, seg_end))
        cursor = max(cursor, e - margin_before)
        cursor = max(cursor, seg_start)
    if cursor < duration:
        keep.append((cursor, duration))

    # Merge segments separated by less than merge_gap (avoids micro-cuts).
    # A tiny floor (0.05s) always applies so exact/near-overlapping segments
    # never produce a zero- or negative-length gap in between.
    gap_threshold = max(0.05, merge_gap)
    merged = []
    for s, e in keep:
        if merged and s - merged[-1][1] < gap_threshold:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))

    # Drop segments shorter than min_keep_duration (likely detection noise)
    final = [(s, e) for s, e in merged if e - s >= min_keep_duration]

    if not final:
        # Safety net: never return an empty edit list
        final = [(0.0, duration)]

    return final


def cut_video(input_path, output_path, keep_segments, cancel_event=None):
    """
    Re-encodes input_path, keeping only keep_segments, via a single
    select/aselect + concat filter graph.
    """
    n = len(keep_segments)
    v_labels = []
    a_labels = []
    filter_parts = []

    for i, (s, e) in enumerate(keep_segments):
        filter_parts.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]"
        )
        filter_parts.append(
            f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]"
        )
        v_labels.append(f"[v{i}]")
        a_labels.append(f"[a{i}]")

    concat_inputs = "".join(f"{v}{a}" for v, a in zip(v_labels, a_labels))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        output_path,
    ]
    returncode, _, stderr = _run(cmd, cancel_event=cancel_event)
    if returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr[-3000:]}")


def process_video(input_path, output_path, silence_db=-30, min_silence_duration=0.35,
                   margin_before=0.22, margin_after=0.1, min_keep_duration=0.25,
                   merge_gap=0.0, cancel_event=None):
    duration = get_duration(input_path, cancel_event=cancel_event)
    silences = detect_silence(input_path, silence_db, min_silence_duration, cancel_event=cancel_event)
    keep_segments = compute_keep_segments(
        duration, silences, margin_before, margin_after, min_keep_duration, merge_gap
    )
    cut_video(input_path, output_path, keep_segments, cancel_event=cancel_event)

    new_duration = sum(e - s for s, e in keep_segments)
    return {
        "original_duration": duration,
        "new_duration": new_duration,
        "removed_duration": duration - new_duration,
        "num_segments_kept": len(keep_segments),
        "num_silences_found": len(silences),
    }


if __name__ == "__main__":
    import sys
    inp, outp = sys.argv[1], sys.argv[2]
    stats = process_video(inp, outp)
    print(stats)
