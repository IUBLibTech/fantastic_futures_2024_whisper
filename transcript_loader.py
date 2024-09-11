import json
import logging
from pathlib import Path
import re

import yaml


def load_transcripts(asset: Path, threeplay: Path) ->list[dict]:
    """Load all of the transcript data for a single asset and return
       them, along with a permutation tuple"""

    transcripts = []
    if not asset.is_dir():
        return transcripts 
    
    if not (asset / "metadata.yaml").exists():
        logging.warning(f"Skipping {asset.name} because there's no metadata.yaml")
        return transcripts

    if asset.name.endswith(".ignore"):
        logging.warning(f"Ignoring {asset}")
        return transcripts


    # load the base metadata
    with open(asset / "metadata.yaml") as f:
        base_meta = yaml.safe_load(f)
    # there's some weirdity where we have "(alternate)" in some of the physical
    # media names.  Let's remove that.
    base_meta['physical format'] = base_meta['physical format'].replace('(alternate)', '').strip()


    # we're going to assume that every media file in this asset has been
    # normalized, so we'll use that as the basis for gathering the 
    # transcripts    
    for nfile in asset.glob("*.normalization.yaml"):
        base_filename = nfile.name
        # remove all of the suffixes.
        for s in reversed(nfile.suffixes):
            base_filename = base_filename[0:-len(s)]
        if '.high' in nfile.name:
            base_filename += ".high"

        # It's great that we're normalized, but without a 3play transcript
        # this is for nothing.  Let's get it if it exists, otherwise move
        # to the next one.
        threeplay_base = base_filename.replace('.', '_')
        if not (threeplay / f"{threeplay_base}.json").exists():
            logging.warning(f"Skipping {asset.name}/{threeplay_base} since there isn't a corresponding 3play transcript")
            continue
        # load threeplay
        threeplay_transcript = load_3play_json(threeplay / f"{threeplay_base}.json")

        # load the normalization
        with open(nfile) as f:
            normalization_meta = yaml.safe_load(f)

        # get the transcript data for each whisper transcript variation
        for tfile in asset.glob(f"{base_filename}.whisper.*.json"):            
            whisper_transcript = load_whisper_json(tfile)
            
            # now that we've collected everything, add it to the list of transcripts
            data = {
                'title': base_meta['title'],
                'physical_format': base_meta['physical format'],
                'content_type': base_meta['content type'],
                'base_filename': base_filename,
                'whisper_model': whisper_transcript['model'],
                'previous_text': whisper_transcript['previous_text'],
                'audio_filter': whisper_transcript['audio_filter'],
                'original_duration': normalization_meta['original_duration'],
                'truncated_duration': normalization_meta['truncated_duration'],
                'whisper_processing_duration': whisper_transcript['runtime'],
                'whisper_transcript': whisper_transcript['text'],
                '3play_transcript': threeplay_transcript,
                # things we'll need later that we might as well compute here.
                'processing_ratio': whisper_transcript['runtime'] / normalization_meta['truncated_duration'],
                'variant': (whisper_transcript['model'], whisper_transcript['audio_filter'], whisper_transcript['previous_text'])
            }
            transcripts.append(data)
    return transcripts


def load_3play_json(file: Path):
    """Load the 3play json file and convert it to plain text without
       audio descriptions or diarization"""
    # 'words' is a list of tuples where I'm assuming the first value is a
    # timestamp of some sort and the 2nd is the word at that timestamp.
    # 'paragraphs' is a list of timestamps where each paragraph starts.
    # 'speakers' is a dict of timestamp -> speaker
    # audio descriptions are single words which match "^\[[A-Z ]+\]$"

    with open(file) as f:
        data = yaml.safe_load(f)

    # filter out words we don't care about
    words = [x for x in data['words'] if x[1] != '']  # empty words
    words = [x for x in words if x[0] not in data['speakers']] # speaker tokens 
    words = [[x[0], re.sub(r'\[\?', ' ', x[1])] for x in words] # remove leading ambiguity marker
    words = [[x[0], re.sub(r'\?\]', ' ', x[1])] for x in words] # remove trailing ambituity marker
    words = [[x[0], re.sub(r'\[.*?\]', ' ', x[1])] for x in words] # remove sound annotation
    words = [[x[0], re.sub(r'</?i>', ' ', x[1])] for x in words] # remove the italic markers
    words = [[x[0], re.sub(r'\([A-Z\s]*\)', ' ', x[1])] for x in words]

    # convert the timestamp to an integer
    words = [[int(x[0]), x[1]] for x in words]


    # split into paragraphs
    paragraphs = [[]]
    data['paragraphs'].append(99999999999)
    for p in range(0, len(data['paragraphs']) - 1):
        p_start = data['paragraphs'][p]
        p_end = data['paragraphs'][p + 1]
        for w in words:
            if p_start <= w[0] < p_end:
                paragraphs[-1].append(w[1])
        paragraphs.append([])
    
    return "\n".join([' '.join(x) for x in paragraphs if len(x)])
    

def load_whisper_json(file: Path, use_text=False,
                      ignore_zero_words=True,
                      ignore_annotations=True) -> dict:
    """Load a whisper transcript file and convert it to the data structure 
    we need for processing."""    
    with open(file) as f:
        raw = json.load(f)    
    
    xscript = raw['_job']
    if use_text:
        xscript['text'] = raw['text']   
    else:
        # normally I just use the text that's generated by whisper, but let's 
        # create the text manually and skip any words with 0 duration...
        text = ""
        words = 0
        duration = 0        
        empty_words = 0
        discarded_words = 0
        # per the internet, people speak 110 - 170 words per minute in english.
        # so, let's assume that someone is speaking really slowly (say, 90
        # words per minute)...we could use that as a cutoff for words that
        # may be really long hallucinations (I've seen 29 second words in
        # whisper and that's clearly wrong).  BUT, whisper will sometimes
        # mis-time the words, so it's not really clear which things are
        # halllucinations and which ones aren't.
        word_duration_cutoff = 60 / 30
        
        # with 2s word cutoff and a 0.5 confidence cutoff, it was too aggressive
        confidence_cutoff = 0.5

        for s in raw['segments']:
            # whisper sound annotations start with '[' for the whole segment, so
            # we can drop the segment if we match that.
            if ignore_annotations and (s['text'].startswith(' [') or
                                       '(*' in s['text']):
                logging.debug(f"Removing sound annotation: {s['text']}")
                continue


            for position, w in enumerate(s['words']):
                words += 1
                word_duration = w['end'] - w['start']
                duration += word_duration
                if ignore_zero_words and word_duration == 0:
                    empty_words += 1
                    continue

                # get rid of music symbol.
                w['word'] = w['word'].replace('♪', ' ')


                # fix OKAY -> OK
                w['word'] = re.sub(r"/bokay/b", 'OK', w['word'], flags=re.IGNORECASE)

                if False and word_duration > word_duration_cutoff:
                    # compute confidence score
                    confidence = w['probability']# * (word_duration_cutoff/ word_duration)
                    logging.info(f"Discarding word '{w['word']}'@{position} {w['probability']*100:0.3f}%  {word_duration:0.3f}s/{word_duration_cutoff:0.3f}s, confidence {confidence * 100:0.3f}%")
                    #if confidence > confidence_cutoff:
                    text += w['word']
                    discarded_words += 1
                    continue
                
                text += w['word']

        logging.debug(f"Whisper text stats for {file}:  {words} words, average {duration/words:0.3f} words per second, {empty_words} were empty, {discarded_words} were discarded for being longer than {word_duration_cutoff:0.3f}")
        xscript['text'] = text

    return xscript
