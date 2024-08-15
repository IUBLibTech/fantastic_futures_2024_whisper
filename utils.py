import json
from pathlib import Path
import subprocess


def get_duration(file: Path):
    p = subprocess.run(["ffprobe", "-show_format", "-show_streams",
                        '-select_streams', 'a:0',
                        "-print_format", "json", str(file.resolve())],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL)
    data = json.loads(p.stdout)
    if 'duration' in data['format']:
        return float(data['format']['duration'])
    # some ffprobes don't put the duration in there...find the audio stream
    for s in data['streams']:
        if s.get("codec_type", None) == "audio" and 'duration' in s:
            return float(s['duration'])
    return 0


def human_time(duration: float) -> str:
    hours = int(duration // 3600)
    duration -= (hours * 3600)
    minutes = int(duration // 60)
    seconds = duration - (60 * minutes)
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"