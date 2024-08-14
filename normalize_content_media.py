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
from utils import get_duration

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("--channels", type=int, default=1, help="Number of audio channels")
    parser.add_argument("--sample_rate", type=int, default=44100, help="Audio Sample Rate")
    parser.add_argument("--sample_size", type=int, default=16, choices=[8, 16, 24, 32], help="Bits per sample")
    parser.add_argument("--silence_threshold", type=int, default=50, help="Silence threshold (positive number in -dB)")
    parser.add_argument("source", type=Path, help="Source root for the media files")
    parser.add_argument("destination", type=Path, help="Destination root for the media files")
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s [%(levelname)-8s] (%(filename)s:%(lineno)d:%(process)d)  %(message)s",
                        level=logging.DEBUG if args.debug else logging.INFO)

    if not all([args.destination.is_dir(), args.source.is_dir()]):
        logging.error("The source and destination must be directories")
        exit(1)
    source: Path = args.source
    dest: Path = args.destination

    # write the normalization parameters to the destination directory
    # so we can reproduce it if needed.
    with open(dest / "normalization_parameters.yaml", "w") as f:
        yaml.safe_dump({'channels': args.channels,
                        'sample_rate': args.sample_rate,
                        'sample_size': args.sample_size,
                        'silence_threshold': args.silence_threshold}, f)
    original_duration = 0
    new_duration = 0

    for sdir in source.glob("*"):        
        ddir = dest / sdir.name
        logging.info(f"Processing {ddir}")
        ddir.mkdir(exist_ok=True)
        # copy any yaml files
        for y in sdir.glob("*.yaml"):
            shutil.copy(y, ddir)
        # convert and strip the media files
        for mediafile in sdir.glob("*.mp4"):
            infile = str(mediafile.resolve())
            tmpfile = (ddir / mediafile.with_suffix(".tmp.wav").name).resolve()
            tmpfile.parent.mkdir(exist_ok=True, parents=True)            
            ffmpeg_command = ["ffmpeg", "-i", infile, "-y",                       
                              "-c:a", f"pcm_s{args.sample_size}le",
                              "-ac", str(args.channels),
                              "-r:a", f"pcm_s{args.sample_rate}le",
                              str(tmpfile)]
            outfile = (ddir /mediafile.with_suffix(".wav").name).resolve()            
            sox_command = ["sox", str(tmpfile), str(outfile),
                           'reverse', 'silence', '1', '1', f'-{args.silence_threshold}dB', 'reverse']
            
            try:
                logging.debug(f"Ffmpeg Command: {ffmpeg_command}")
                p = subprocess.run(ffmpeg_command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   check=True, encoding="utf-8")
                logging.debug(f"SOX Command: {sox_command}")
                p = subprocess.run(sox_command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   check=True, encoding="utf-8")
                oduration = get_duration(mediafile)
                original_duration += oduration
                nduration = get_duration(outfile)
                new_duration += nduration
                logging.info(f"Normalizing {mediafile.name}: {oduration:0.3f} -> {nduration:0.3f}")
            except Exception as e:
                logging.exception(f"Cannot transcode {mediafile}: {e}")
            finally:
                tmpfile.unlink(missing_ok=True)

    logging.info(f"Total duration of normalized data: {new_duration:0.3f}, {original_duration-new_duration:0.3f} seconds less than original")


if __name__ == "__main__":
    main()