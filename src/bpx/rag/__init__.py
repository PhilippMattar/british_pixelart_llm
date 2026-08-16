"""Adaptive RAG (Elective 1, PLAN.md §10): judge -> rewrite -> multiturn retrieval -> summarize.

Embeddings via nomic-embed-text (Ollama); vectors stored as float32 BLOBs in the one SQLite file
and ranked by brute-force cosine in Python (this Python's sqlite3 can't load sqlite-vec, and an
ANN index is unnecessary at this scale).
"""
