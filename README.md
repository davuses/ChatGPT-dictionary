## Changes to tts library

Switch to nltk to split sentences.

skip sentences that are too short or long

*synthesizer.py*
"""py
sens = self.split_into_sentences(text)
sens = [sen for sen in sens if (len(sen) >= 30 and len(sen) <= 250)]
if len(sens) >= 5:
    sens = sens[:5]
"""

## Libraries

[Markdown css themes](https://github.com/jasonm23/markdown-css-themes)

[Markdown Editor](https://github.com/devhau/md-editor#keyboard-shortcuts)
