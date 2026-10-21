"""The lineup file: unique ids, known labs and harnesses, and no model that falls back."""
from slopvestigator_bench import lineup

EXCLUDED = {"claude-opus-5-5", "claude-fable-5-1"}  # switch to Opus 4.8 on safety refusals


def test_lineup_is_well_formed():
    models = lineup.models()
    assert len(models) == 13 and len({m.id for m in models}) == 13
    assert not EXCLUDED & {m.id for m in models}
    assert {m.harness for m in models if m.lab == "anthropic"} == {"claude"}
    assert {m.harness for m in models if m.lab == "openai"} == {"codex"}
    assert all(m.price_in > 0 and m.price_out > 0 and m.colour.startswith("#") for m in models)
    assert lineup.model("gpt-6.1-sol").label == "GPT-6.1 Sol"
