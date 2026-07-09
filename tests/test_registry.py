from pathlib import Path

from bpx.registry import Registry, client_for


def test_registry_loads_from_toml(tmp_path: Path) -> None:
    toml = tmp_path / "models.toml"
    toml.write_text(
        """
[[models]]
name = "base"
provider = "ollama"
endpoint = "http://localhost:11434/v1"
model_id = "qwen3.5:4b"

[[models]]
name = "british"
provider = "ollama"
endpoint = "http://localhost:11434/v1"
model_id = "bpx-british"
is_persona = true
keywords = ["innit", "mate"]
""",
        encoding="utf-8",
    )
    reg = Registry.load(toml)
    assert reg.names() == ["base", "british"]
    british = reg.get("british")
    assert british.is_persona is True
    assert british.keywords == ("innit", "mate")


def test_default_registry_when_file_missing(tmp_path: Path) -> None:
    reg = Registry.load(tmp_path / "does-not-exist.toml")
    assert "base" in reg.names()


def test_local_spec_uses_placeholder_key() -> None:
    reg = Registry.load(Path("does-not-exist.toml"))
    spec = reg.get("base")
    assert spec.api_key == "ollama"  # local placeholder; Ollama ignores it
    client = client_for(spec)
    assert client.model_id == spec.model_id
