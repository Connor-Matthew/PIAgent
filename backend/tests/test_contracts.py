"""Tests for backend.nodes.contracts — Node Contract definitions."""

from __future__ import annotations

import pytest

from backend.nodes.contracts import (
    NODE_CONTRACTS,
    ConfigFieldDef,
    InputRefDef,
    OutputFieldDef,
    NodeContract,
    get_contract,
    list_contracts,
)


# ── Basic registry tests ──


def test_all_registered_node_types_have_contracts():
    from backend.nodes.registry import node_registry

    registered = set(node_registry.list_types())
    contracted = set(NODE_CONTRACTS.keys())
    # Test-only mock nodes may exist without contracts — that's expected.
    missing = registered - contracted
    test_only = {
        "template_echo", "conditional_fail", "delay_echo",
        "echo", "echo_v2", "barrier_fail", "counting",
        "mock_llm", "mock_tts", "fake", "duplicate",
        "exploding", "side_effect",
    }
    unexpected = missing - test_only
    assert not unexpected, f"Missing contracts for: {unexpected}"


def test_get_contract_existing():
    contract = get_contract("llm")
    assert contract.node_type == "llm"
    assert contract.description != ""


def test_get_contract_unknown_raises():
    with pytest.raises(KeyError, match="No contract defined"):
        get_contract("nonexistent")


def test_list_contracts_returns_all():
    contracts = list_contracts()
    assert len(contracts) == len(NODE_CONTRACTS)
    types = {c.node_type for c in contracts}
    assert types == set(NODE_CONTRACTS.keys())


# ── Contract completeness ──


def test_llm_contract_has_prompt_template():
    contract = get_contract("llm")
    field_names = {f.name for f in contract.config_fields}
    assert "prompt_template" in field_names

    prompt_field = next(f for f in contract.config_fields if f.name == "prompt_template")
    assert prompt_field.type == "string"
    assert prompt_field.default == ""


def test_rag_contract_has_query_ref():
    contract = get_contract("rag")
    field_names = {f.name for f in contract.config_fields}
    assert "query_ref" in field_names

    ref_field = next(f for f in contract.config_fields if f.name == "query_ref")
    assert ref_field.type == "string"
    assert ref_field.default == ""


def test_tts_contract_has_text_ref():
    contract = get_contract("tts")
    field_names = {f.name for f in contract.config_fields}
    assert "text_ref" in field_names

    ref_field = next(f for f in contract.config_fields if f.name == "text_ref")
    assert ref_field.type == "string"
    assert ref_field.default == ""


def test_end_contract_source_enum_is_static():
    """End node contract should not mention 'input' as source value."""
    contract = get_contract("end")
    outputs_field = next(f for f in contract.config_fields if f.name == "outputs")
    assert "static" in outputs_field.description
    assert "reference" in outputs_field.description


# ── Input refs ──


def test_llm_contract_has_input_ref_for_prompt_template():
    contract = get_contract("llm")
    ref_fields = {r.config_field for r in contract.input_refs}
    assert "prompt_template" in ref_fields


def test_rag_contract_has_input_ref_for_query_ref():
    contract = get_contract("rag")
    ref_fields = {r.config_field for r in contract.input_refs}
    assert "query_ref" in ref_fields


def test_tts_contract_has_input_ref_for_text_ref():
    contract = get_contract("tts")
    ref_fields = {r.config_field for r in contract.input_refs}
    assert "text_ref" in ref_fields


# ── Output fields ──


def test_llm_outputs_text():
    contract = get_contract("llm")
    out_names = {o.name for o in contract.output_fields}
    assert "text" in out_names


def test_rag_outputs_context_and_documents():
    contract = get_contract("rag")
    out_names = {o.name for o in contract.output_fields}
    assert "context" in out_names
    assert "documents" in out_names


def test_tts_outputs_audio_url_and_duration():
    contract = get_contract("tts")
    out_names = {o.name for o in contract.output_fields}
    assert "audio_url" in out_names
    assert "duration" in out_names


# ── JSON Schema generation ──


def test_to_json_schema_includes_properties():
    contract = get_contract("llm")
    schema = contract.to_json_schema()
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "provider_id" in schema["properties"]
    assert "prompt_template" in schema["properties"]


def test_to_json_schema_includes_required():
    contract = get_contract("llm")
    schema = contract.to_json_schema()
    assert "required" in schema
    assert "provider_id" in schema["required"]


def test_to_json_schema_includes_defaults():
    contract = get_contract("llm")
    schema = contract.to_json_schema()
    props = schema["properties"]
    assert props["model"]["default"] == "gpt-4o"
    assert props["temperature"]["default"] == 0.7


def test_to_json_schema_includes_enum():
    contract = get_contract("tts")
    schema = contract.to_json_schema()
    props = schema["properties"]
    assert "emotion" in props
    assert props["emotion"]["enum"] == ["happy", "sad", "angry", "neutral"]


# ── Serialization ──


def test_contract_can_be_serialized():
    contract = get_contract("start")
    data = contract.model_dump(mode="json")
    assert data["node_type"] == "start"
    assert "config_fields" in data
    assert "input_refs" in data
    assert "output_fields" in data
