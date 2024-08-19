#!/bin/env python3
"""
Walk through the media files and convert them into a consistent format.
This will also strip silence from the end.
"""
import argparse
import json
import logging
from pathlib import Path
import shutil
import subprocess
import yaml
from utils import get_duration, human_time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("--silence_threshold", type=int, default=60, help="Silence threshold (positive number in -dB)")
    parser.add_argument("--pop_length", type=float, default=0.2, help="Length of pops to be ignored")
    parser.add_argument("--adaptive_gap", default=False, action="store_true", help="Use adaptive pop management")
    parser.add_argument("--adaptive_factor", default=1.0, type=float, help="adaptive gap factor multiplier")
    parser.add_argument("source", type=Path, help="Source for the media files")    
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s [%(levelname)-8s] (%(filename)s:%(lineno)d:%(process)d)  %(message)s",
                        level=logging.DEBUG if args.debug else logging.INFO)

    if not args.source.is_dir():
        logging.error("The source and destination must be directories")
        exit(1)
    source: Path = args.source
    

    # write the normalization parameters to the destination directory
    # so we can reproduce it if needed.
    with open(source / "normalization_parameters.yaml", "w") as f:
        yaml.safe_dump({'silence_threshold': args.silence_threshold,
                        'pop_length': args.pop_length,
                        'adaptive_gap': args.adaptive_gap,
                        'adaptive_factor': args.adaptive_factor}, f)
    
    original_duration = 0
    new_duration = 0

    for sdir in source.glob("*"):                
        logging.info(f"Processing {sdir}")        
        # convert and strip the media files
        for mediafile in sdir.glob("*.mp4"):
            try:
                duration = get_duration(mediafile)
                original_duration += duration
                p = subprocess.run(["ffmpeg", "-i", str(mediafile.resolve()),
                                    '-af', f'silencedetect=noise=-{args.silence_threshold}dB',
                                    '-f', 'null', '-'],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, encoding='utf-8',
                                    check=True)
                segments = []
                for l in p.stdout.splitlines():
                    if 'silence_duration' in l:
                        parts = l.split()
                        s = {'start': float(parts[4]) - float(parts[7]),
                             'end': float(parts[4])}
                        segments.append(s)
                
                nduration = duration
                
                
                if args.adaptive_gap:
                    for seg in reversed(segments):
                        l = (seg['end'] - seg['start']) * args.adaptive_factor
                        if nduration - seg['end'] < l:
                            logging.debug(f"Setting duration to {seg['start']} because gap between segment and duration ({nduration - seg['end']}) is less than {l}")
                            nduration = seg['start']
                        else:
                            break
                else:
                    for seg in reversed(segments):
                        #print("Testing segment: ", seg)                    
                        if nduration - args.pop_length < seg['end']:
                            # there's a pop (or overlap) at the end..move the duration.
                            #print(f"test point at {cpoint} is less than the end..")
                            nduration = seg['start']
                        else:
                            #print("segment is out of bound")
                            break
                
                
                new_duration += nduration
                logging.debug(f"{duration}, {nduration}, {segments}")
                                
                tfile = mediafile.with_suffix(".tmp")
                mediafile.rename(tfile)
                p = subprocess.run(['ffmpeg', '-i', str(tfile.resolve()), '-y',
                                    '-c:a', 'copy', '-c:v', 'copy', 
                                    '-t', str(nduration), str(mediafile.resolve())],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=True,
                                    encoding='utf-8')
                tfile.unlink(missing_ok=True)
                # write the normalization information
                with open(mediafile.parent / f"{mediafile.name}.normalization.yaml", "w") as f:
                    yaml.safe_dump({'filename': str(mediafile),
                                    'original_duration': duration,
                                    'truncated_duration': nduration}, f)
                logging.info(f"Removed trailing silence:  {human_time(duration)} -> {human_time(nduration)} (reduction: {human_time(duration - nduration)})")

            except Exception as e:
                logging.exception(f"Cannot transcode {mediafile}: {e}")

    logging.info(f"Total duration of normalized data: {human_time(new_duration)}, {human_time(original_duration-new_duration)} less than original")


if __name__ == "__main__":
    main()