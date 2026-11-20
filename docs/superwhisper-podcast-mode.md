# Superwhisper Podcast mode

podscribe's default analyzer hands audio to Superwhisper and reads both
results of one pass: the transcript and the analysis from a Custom Mode.
The analysis comes from the mode prompt below. To reproduce it, create a
Custom Mode in Superwhisper with these settings:

| Setting | Value |
| --- | --- |
| Name | `Podcast` |
| Key | `podcast` |
| Type | `custom` |
| Language | `en` |
| Voice model | `Scribe` (cloud) |
| Language model | `GPT-6 Luna` |
| Prompt | see below |

## Prompt

```text
Reformat the user's message. Fix grammar, spelling, and punctuation. Remove filler words like "um" and "uh". Break long content into paragraphs. Keep the original tone and meaning. Only output the cleaned text, nothing else.
```

The key `podcast` is what podscribe writes as `analyzer.superwhisper.mode_key`
in `config.yaml`.

## What this mode produces

The Podcast mode is a cleanup pass: it fixes punctuation and filler words,
so it yields no summary. An analyzer that summarises can replace the prompt
with its own instruction; podscribe renders whatever Markdown comes back.

This prompt emits no `CATEGORY:` or `FILENAME:` header lines. podscribe's
header stripper exists for other analyzers and leaves this mode's text
unchanged.
