#!/bin/env python3
"""
Run whisper on the files
"""
import argparse
import json
import logging
from pathlib import Path
import shutil
import subprocess
import yaml
from utils import get_duration, human_time
import whisper
import torch
import time

supported_languages = ['en', 'zh', 'de', 'es', 'ru', 'ko', 'fr', 'ja']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("--model", default="medium", 
                        choices=['tiny', 'tiny.en', 'base', 'base.en', 'small', 
                                 'small.en', 'medium', 'medium.en', 'large',
                                 'large-v1', 'large-v2', 'large-v3'],
                        help="Language Model to use")
    parser.add_argument("--language", default="auto",
                        choices=('auto', *supported_languages),
                        help="Language to use or 'auto' to detect")
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

    # add our parameter metadata
    with open(dest / "whisper_parameters.yaml", "w") as f:
        yaml.safe_dump({'model': args.model,
                        'language': args.language}, f)    

    # Set up whisper
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logging.info(f"Whisper will use {device} for computation")
    logging.info(f"Loading model {args.model}")
    model = whisper.load_model(args.model, device=device)

    file_count = 0
    start_time = time.time()
    for sdir in source.glob("*"):
        if not sdir.is_dir():
            continue    
        ddir = dest / sdir.name
        logging.info(f"Processing {ddir}")
        ddir.mkdir(exist_ok=True)
        # copy any yaml files
        for y in sdir.glob("*.yaml"):
            shutil.copy(y, ddir)
        

        for media_file in sdir.glob("*.wav"):
            logging.info(f"Transcribing {media_file.name}")
            start = time.time()
            duration = get_duration(media_file)
            file_count += 1
            audio = whisper.load_audio(str(media_file))
            if args.language == 'auto':
                detect_audio = whisper.pad_or_trim(audio)
                mel = whisper.log_mel_spectrogram(detect_audio,
                                                  n_mels=128 if args.model in('large', 'large-v3') else 80,
                                                  device=device).to(device)
                _, probs = model.detect_language(mel)
                # limit to our supported languages
                probs = {k: v for k, v in probs.items() if k in supported_languages}
                language = max(probs, key=probs.get)
                logging.info(f"Detected language {language}")
            else:
                language = args.language

            res = whisper.transcribe(model, audio, 
                                     word_timestamps=True,
                                     language=language)
            res['_job'] = {
                'runtime': time.time() - start,
                'duration': duration,
                'device': device,
                'language': language,
                'detected': args.language == 'auto',
                'model': args.model                
            }
            with open(ddir / f"{media_file.name}.whisper", "w") as f:
                json.dump(res, f, indent=4)
            logging.info(f"Finished transcribing.  {human_time(duration)} of content in {human_time(res['_job']['runtime'])}")

            
    logging.info(f"{file_count} files processed, total content duration {human_time(duration)}, run time {human_time(time.time() - start_time)}")


if __name__ == "__main__":
    main()