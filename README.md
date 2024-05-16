## Changes to tts library

Switch to nltk to split sentences.

skip sentences that are too short or long

synthesizer.py
"""
sens = self.split_into_sentences(text)
sens = [sen for sen in sens if (len(sen) >= 30 and len(sen) <= 250)]
if len(sens) >= 5:
    sens = sens[:5]
"""
