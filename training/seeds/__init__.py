"""Seed style corpora — authentic-voice snippets used as few-shot exemplars for the teacher.

`exemplars.py` holds a small HAND-WRITTEN bootstrap set so the humor spike needs no external
data. The real run expands these with collected corpora (Reddit via Arctic Shift, Project
Gutenberg dry wit, SCOTS) via collection/cleaning scripts — raw corpora are never committed
(PLAN.md §3, §6.1); only the scripts and the cleaned, shippable exemplars are.
"""
