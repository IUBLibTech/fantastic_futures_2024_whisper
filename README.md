# fantastic_futures_2024_whisper
Tools for the fantastic futures 2024 whisper presentation

Tools/Steps:

## load_content
Grabs all of the content for the selected items from HCP/SCP listed in the 
spreadsheets 

## normalize_content_media
Strip the trailing silence from the end of the media files.  The algorithm
boils down to:
* Find all of the silence segments
* starting at the end and working backward look at each silence segment:
    * Get the length of the non-silence duration between the end of the silence
      segment and the computed duration
    * If the length is less than the duration of the silence segment, then it's
      inconsequential noise and reset the computed duration to the start of the
      silence segment (i.e. shorten the file)
    * If it isn't, then it's real audio and we stop recomputing the duration
* cut the file at the computed duration and replace the original file.
* The metadata 

