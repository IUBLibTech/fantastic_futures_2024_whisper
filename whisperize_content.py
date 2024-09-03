#!/bin/env python3
"""
Run whisper on the files
"""
import argparse
import json
import logging
from pathlib import Path
import subprocess
from utils import get_duration, human_time
import whisper
import torch
import time
from tempfile import NamedTemporaryFile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", default=False, action="store_true", help="Turn on debugging")
    parser.add_argument("--resume", default=False, action="store_true", help="Resume where it left off")
    parser.add_argument("workdir", type=Path, help="Root for the media files")
    
    args = parser.parse_args()
    logging.basicConfig(format="%(asctime)s [%(levelname)-8s] (%(filename)s:%(lineno)d:%(process)d)  %(message)s",
                        level=logging.DEBUG if args.debug else logging.INFO)

    if not args.workdir.is_dir():
        logging.error("The workdir must be a directory")
        exit(1)
    
    workdir: Path = args.workdir
    
    if args.resume:
        # determine the time of the newest whisper file and set the cutoff time
        # to one second prior to that (in case we were killed while writing
        # that transcript file)
        file_times = [0]
        for f in workdir.glob("**/*.whisper.*.json"):
            file_times.append(f.stat().st_mtime)
        resume_time = max(file_times) - 1
    else:
        resume_time = 0




    # Set up whisper
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logging.info(f"Whisper will use {device} for computation")
    
    
    # Run through all of the permutations...
    for model_name in ('small', 'medium', 'large-v2', 'large-v3'):
        logging.info(f"Loading model {model_name}")
        model = whisper.load_model(model_name, device=device)

        for media_file  in workdir.glob("*/*"):
            if media_file.suffix not in (".wav", ".mp4"):
                logging.debug(f"Skipping file: {media_file}")
                continue

            for audio_filter, audio_filter_args in {'X': [],
                                                    'A': ['-af', 'afftdn=nr=10:nf=-25:tn=1'],
                                                    'B': ['-af', 'volume=4']}.items():
                # Apply the audio filter.  
                with NamedTemporaryFile(suffix=".wav") as tempfile:
                    p = subprocess.run(['ffmpeg', '-y', '-i', str(media_file), *audio_filter_args,
                                        '-c:a', 'pcm_s16le', '-ar', '44100', '-ac', '2', tempfile.name],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, encoding='utf-8')
                    if p.returncode != 0:
                        logging.error(f"Cannot filter {media_file} with {audio_filter_args}: {p.stdout}")
                        continue

                    for previous_text in ('T', 'F'):
                        logging.info(f"Transcribing {media_file} with model {model_name}, previous_text {previous_text}, audio_filter: {audio_filter}")
                        whisper_file = media_file.with_suffix(f".whisper.{model_name}_{previous_text}_{audio_filter}.json")
                        if whisper_file.stat().st_mtime < resume_time:
                            logging.info(f"Skipping creation of {whisper_file.name} since it already exists")
                            continue

                        
                        whisper_start = time.time()
                        duration = get_duration(media_file)
                        audio = whisper.load_audio(tempfile.name)
                        #detect_audio = whisper.pad_or_trim(audio)
                        #mel = whisper.log_mel_spectrogram(detect_audio,
                        #                                n_mels=128 if model_name in('large', 'large-v3') else 80,
                        #                                device=device).to(device)
                        #_, probs = model.detect_language(mel)
                        #language = max(probs, key=probs.get)
                        #logging.info(f"Detected language {language}")
                        language = "en"
            
                        res = whisper.transcribe(model, audio, 
                                                word_timestamps=True,
                                                language=language,
                                                condition_on_previous_text=previous_text==True)
                        res['_job'] = {
                            'runtime': time.time() - whisper_start,
                            'duration': duration,
                            'device': device,
                            'language': language,
                            'model': model_name,
                            'previous_text': previous_text,
                            'audio_filter': audio_filter                
                        }
                        with open(whisper_file, "w") as f:
                            json.dump(res, f, indent=4)
                        logging.info(f"Finished transcribing {media_file}.  {human_time(duration)} of content in {human_time(res['_job']['runtime'])}")
    
        logging.info(f"Unloading Whisper Model")
        del(model)
        if device == "cuda":
            torch.cuda.empty_cache()
    

if __name__ == "__main__":
    main()