#!/bin/env python3
"""
Walk through the media files and select the ones we want to use.  
Emily says that we're just looking at the first media file for each of these,
but we may change our minds later, so automation-ahoy!
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

    # copy any metadata/parameters from the source dir
    for f in source.glob("*.yaml"):
        shutil.copy(f, dest)

    duration = 0
    file_count = 0
    for sdir in source.glob("*"):
        if not sdir.is_dir():
            continue    
        ddir = dest / sdir.name
        logging.info(f"Processing {ddir}")
        ddir.mkdir(exist_ok=True)
        # copy any yaml files
        for y in sdir.glob("*.yaml"):
            shutil.copy(y, ddir)
        media_files = sorted(list(sdir.glob("*.wav")), key=lambda x: x.name)
        if media_files:
            duration += get_duration(media_files[0])
            file_count += 1
            shutil.copy(media_files[0], ddir)        

    logging.info(f"{file_count} files copied, total duration {human_time(duration)}")


if __name__ == "__main__":
    main()