from bpx.llm import Message
from bpx.memory import dedup_new, extract_facts, parse_facts, system_prompt


def test_parse_facts_extracts_array_and_tolerates_prose():
    assert parse_facts('["a", "b"]') == ["a", "b"]
    assert parse_facts('Sure, here you go: ["x"]  done') == ["x"]
    assert parse_facts("no json at all") == []
    assert parse_facts("[not valid json") == []
    assert parse_facts('[1, "keep", "", true]') == ["keep"]  # only non-empty strings


def test_dedup_new_filters_existing_and_within_batch():
    # case/punctuation-insensitive match against existing
    assert dedup_new(["The user likes tea", "brand new"], ["the user likes tea."]) == ["brand new"]
    assert dedup_new(["dup", "dup"], []) == ["dup"]  # within-batch duplicate dropped


def test_system_prompt_none_when_empty_else_lists_facts():
    assert system_prompt([]) is None
    prompt = system_prompt(["fact one", "fact two"])
    assert "fact one" in prompt and "fact two" in prompt


class _FakeLLM:
    def __init__(self, completion):
        self._completion = completion

    async def complete(self, messages):
        return self._completion


class _BoomLLM:
    async def complete(self, messages):
        raise RuntimeError("network down")


async def test_extract_facts_returns_deduped_new_facts():
    client = _FakeLLM('["The user is Sam"]')
    got = await extract_facts(client, [], [Message("user", "hi, I'm Sam")])
    assert got == ["The user is Sam"]

    # already known -> nothing new
    got2 = await extract_facts(client, ["the user is sam"], [Message("user", "hello again")])
    assert got2 == []


async def test_extract_facts_empty_transcript_skips_llm():
    assert await extract_facts(_BoomLLM(), [], []) == []  # no messages -> no call, no raise


async def test_extract_facts_swallows_llm_errors():
    assert await extract_facts(_BoomLLM(), [], [Message("user", "hi")]) == []
