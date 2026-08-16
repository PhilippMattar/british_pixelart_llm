from bpx.rag import pipeline
from bpx.rag.chunk import chunk_text, read_document
from bpx.rag.embed import from_blob, to_blob
from bpx.store import Store

MARKERS = ("apple", "banana", "cherry")


class _FakeEmbedder:
    """Deterministic keyword-count embeddings, so cosine ranking is predictable in tests."""

    async def embed(self, texts):
        return [[float(t.lower().count(m)) for m in MARKERS] + [1.0] for t in texts]

    async def embed_one(self, text):
        return (await self.embed([text]))[0]


class _RoutingClient:
    """Fake LLM that answers each pipeline step based on the prompt it receives."""

    def __init__(self, route="LOCAL"):
        self.route = route

    async def complete(self, messages):
        p = messages[0].content
        if "One word:" in p:
            return self.route
        if "Search query:" in p:
            return "apple facts"
        if "Reply only YES or NO" in p:
            return "YES"
        if "Relevant notes:" in p:
            return "- Apples are red [1]"
        return ""


# ---- chunking / io ----
def test_chunk_text_overlaps_and_handles_empty():
    words = " ".join(f"w{i}" for i in range(1000))
    chunks = chunk_text(words, chunk_words=100, overlap_words=20)
    assert len(chunks) > 1
    assert chunks[0].split()[-20:] == chunks[1].split()[:20]  # overlap carried over
    assert chunk_text("") == []


def test_read_document_reads_text(tmp_path):
    f = tmp_path / "d.txt"
    f.write_text("hello world")
    assert read_document(str(f)) == "hello world"


# ---- vectors ----
def test_blob_roundtrip():
    vec = [0.5, -1.25, 3.0]
    assert from_blob(to_blob(vec)) == vec


def test_cosine_ranks_parallel_over_orthogonal():
    assert pipeline.cosine([1, 0], [2, 0]) == 1.0
    assert pipeline.cosine([1, 0], [0, 1]) == 0.0


# ---- retrieval + ingestion against a real store, fake embedder ----
async def test_ingest_then_retrieve_nearest(tmp_path):
    store = Store.open(tmp_path / "r.db")
    pid = store.default_project_id()
    emb = _FakeEmbedder()
    # two docs with distinct keyword profiles
    (tmp_path / "a.txt").write_text("apple apple apple")
    (tmp_path / "b.txt").write_text("banana banana banana")
    await pipeline.ingest_document(store, emb, pid, str(tmp_path / "a.txt"))
    await pipeline.ingest_document(store, emb, pid, str(tmp_path / "b.txt"))

    hits = await pipeline.retrieve(store, emb, pid, "apple", k=1)
    assert hits[0].document_title == "a.txt"
    store.close()


async def test_build_context_local_returns_sources(tmp_path):
    store = Store.open(tmp_path / "r.db")
    pid = store.default_project_id()
    emb = _FakeEmbedder()
    (tmp_path / "a.txt").write_text("apple apple apple")
    await pipeline.ingest_document(store, emb, pid, str(tmp_path / "a.txt"))

    result = await pipeline.build_context(_RoutingClient("LOCAL"), emb, store, pid, "apples?", [])
    assert result is not None
    assert "[1]" in result.context
    assert result.sources and "a.txt" in result.sources[0]
    store.close()


async def test_build_context_direct_returns_none(tmp_path):
    store = Store.open(tmp_path / "r.db")
    pid = store.default_project_id()
    emb = _FakeEmbedder()
    (tmp_path / "a.txt").write_text("apple apple apple")
    await pipeline.ingest_document(store, emb, pid, str(tmp_path / "a.txt"))

    result = await pipeline.build_context(_RoutingClient("DIRECT"), emb, store, pid, "hi", [])
    assert result is None
    store.close()
