# Whisper Transcription Options

## Model
* tiny
* small
* base
* medium -- we've had pretty good results with this one
* large (aka large-v3)
* large-v2


## initial_prompt
default: None
```
Optional text to provide as a prompt for the first window. This can be used to provide, or
"prompt-engineer" a context for transcription, e.g. custom vocabularies or proper nouns
to make it more likely to predict those word correctly.
```

This does impact the output to some extent, but it doesn't seem to behave in
any way that's totally predictable.
* Prompts with no punctuation tends to getnerate the first part in all lower
  case with no punctuation, but then would go back to normal later.
* Prompts with numbers 
  `One. Two. Three. Four. Five. Six. Seven. Eight. Nine.   Ten. 11. 12. 20. 100. 200. 1000. 2000. 10000. 20000.  100000. 200000.` 
  Used digits for the numbers found but didn't necessarily do them in the format
  presented (i.e. `25,000`)
* I can't seem to impact capitalization
* I couldn't get it to find proper names "Payne" and "Castle" in my test audio.

There's a possibility that different impacts for different parameters, but I'm 
not seeing a huge benefit here.

## temperature
default: (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
```
Temperature for sampling. It can be a tuple of temperatures, which will be successively used
upon failures according to either `compression_ratio_threshold` or `logprob_threshold`.
```
Per the web:
```
The sampling temperature, between 0 and 1. Higher values like 0.8 will make the 
output more random, while lower values like 0.2 will make it more focused and 
deterministic. If set to 0, the model will use log probability to automatically 
increase the temperature until certain thresholds are hit
```
According to various sources, very low values (0.1) might lead to a higher probability 
of it getting stuck in a loop....i.e. the stuttering hallucinations.

When there's a list given, it will go to the next value if either of the aforementioned
thresholds are failed, so it goes from very deterministic to less so.

Setting it "1.0" definitely added some randomness to the transcription...where
some words are better (this is dictation audio, hence "colon" and "comma"):
* Default:
  ```
  another thing that hinders our finding them is that most of them are of the 
  type that we call recessive colon that is comma an individual does not show 
  the mutant characteristic unless he has inherited the same kind of gene.
  ```
* Temperature 1.0:
  ```
  Another thing that hinders our finding then is that most of them are of the 
  type that call resuscitin. An individual does not show the mutant 
  characteristic unless he has inherited the same kind of...
  ```


## compression_ratio_threshold
default: 2.4
```
If the gzip compression ratio is above this value, treat as failed
```
This is a ratio of how well the output compresses...basically it's a measurement
of how repeating it is.

`compression_ratio = len(text)/len(zlib.compress(text.encode('utf-8')))`

The more repeating it is, the higher it will compress and then cause a failure,
which will then bump the temperature up by the next interval (default: +0.2) and
thus introduce more randomness to the transcription.  

This seems like a dead man's switch for when it starts repeating itself ad 
infinitum.  When this is triggered it should get out of the repetition loop.


## logprob_threshold
default: -1.0
```
If the average log probability over sampled tokens is below this value, treat as failed
```

Like the compression_ratio_threshold, this will cause the segment to be re-inferenced
and re-decoded.  I don't understand exactly how it works, but it does seem to
be a measure of confidence...and if it's a log value, then -1.0 would be a
10% confidence (10^-1 = 0.1)


## no_speech_threshold
default: 0.6
```
If the no_speech probability is higher than this value AND the average log probability
over sampled tokens is below `logprob_threshold`, consider the segment as silent
```

This seems to catch when it's generating low-confidence content (logprob_threshold < 10%)
and it seems that it's likely non-speech (no_speech > 60) that it should just
stop what it's doing and move on to the next segment and ignore this bit.


## condition_on_previous_text
default: True
```
if True, the previous output of the model is provided as a prompt for the next window;
disabling may make the text inconsistent across windows, but the model becomes less prone to
getting stuck in a failure loop, such as repetition looping or timestamps going out of sync.
```
This is self-prompting.  Here's the default transcription:
```
One reason why the little fruit flies comma, derisaphala, comma, comma, correction, 
the chief reasons why, were introduced into the study of heredity and mutation 
in the early work of pain and castle and more
```
But when it's false...
```
One reason why the little fruit flies, kamadur-saffla, kamadur-kama, the chief 
reasons why, were introduced into the study of heredity and mutation in the 
early work of pain, the castle, and more
```

Because the token 'comma' was probably enunciated clearly earlier in the audio
(likely more than once), the first example has a better grip on what makes more
sense in this context.


## clip_timestamps
default: "0"
```
Comma-separated list start,end,start,end,... timestamps (in seconds) of clips to process.
The last end timestamp defaults to the end of the file.
```

This looks like a shortcut when we need to grab only parts of the file without
chopping it up.  It only seems to be present in the API but not the command line
tool, so I'm not sure how it works.



## hallucination_silence_threshold
default: None
```
When word_timestamps is True, skip silent periods longer than this threshold (in seconds)
when a possible hallucination is detected
```

Only available via API (which is fine because I use it)


## other decode options
Keyword-based options

### beam_size
default: 5
```
number of beams in beam search, only applicable when temperature is zero
```

In a beam search, the top-n nodes are traversed in the tree at each level, rather
than trying all of the results.  This reduces search time and memory requirements
with the downside that the "best result" may get pruned.  So increasing the beam
may end up with better results (such as the reduction of hallucinations others
have reported), but at the cost of memory/time
https://en.wikipedia.org/wiki/Beam_search


### patience
default: None
```
optional patience value to use in beam decoding, as in https://arxiv.org/abs/2204.05424, 
the default (1.0) is equivalent to conventional beam search
```
This is effectively a tunable to stop the tree search early.  I'm not sure what
the value actually does, but since 1.0 is a full beam search, one would assume
that 0.5 would do half as much, probably in terms of depth since beam_width
and best_of seem to handle the width aspect.



### best_of
default: 5
```
number of candidates when sampling with non-zero temperature
```
This seems to be the equivalent to the beam_size but when temperature is not
zero (beam only applies when temperature is zero).


### length_penalty
default: None
```
optional token length penalty coefficient (alpha) as in https://arxiv.org/abs/1609.08144, 
uses simple length normalization by default
```

According to the link above, this looks like it controls the behavior that
"encourages generation of an output sentence that is most likely to cover all 
the words in the source sentence"