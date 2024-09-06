Whisper hallucinations are often words with zero seconds duration.  Filtering
them will often improve the WER by ~1%

3play adds some commentary that's not in the text itself:
From 01-01-40000003402619.plain_text.txt  (beach wastes library)
```
[CHEERING, APPLAUSE] 

I am grateful to you. But I feel no exaltation, no sense of triumph. Our trouble
s are all ahead of us. That we are now on the eve of great decisions, not easy d
ecisions, like resistance when you are attacked, but a long, patient, costly str
uggle which alone can assure triumph over the great enemies of man, war, poverty
, and tyranny, and the assaults upon human dignity which are the most grievous c
onsequences of each. I shall always try-- 

[ELLA FITZGERALD, "I'M BEGINNING TO SEE THE LIGHT"] 

(SINGING) I never cared much for moonlit skies 
```

These are separate tokens, so I'm going to assume that any token in [] or ()
which doesn't contain lower case letters is a description.
