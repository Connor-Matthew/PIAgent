import pytest
from backend.core.template import resolve_reference, render_template
from backend.core.state import WorkflowState


def test_resolve_reference_node_output():
    state: WorkflowState = {
        "node_outputs": {
            "llm_1": {"text": "Hello, world!"},
            "tts_1": {"audio_url": "/audio/1.mp3"},
        }
    }
    assert resolve_reference("{{llm_1.text}}", state) == "Hello, world!"
    assert resolve_reference("{{tts_1.audio_url}}", state) == "/audio/1.mp3"


def test_resolve_reference_local_vars_priority():
    state: WorkflowState = {
        "inputs": {"title": "from inputs"},
        "node_outputs": {"end_1": {"title": "from node_outputs"}},
    }
    local_vars = {"title": "from local"}
    assert resolve_reference("{{title}}", state, local_vars) == "from local"


def test_resolve_reference_inputs_fallback():
    state: WorkflowState = {
        "inputs": {"topic": "AI podcast"},
    }
    assert resolve_reference("{{topic}}", state) == "AI podcast"


def test_resolve_reference_missing_returns_empty():
    state: WorkflowState = {"node_outputs": {}}
    assert resolve_reference("{{missing.field}}", state) == ""
    assert resolve_reference("{{missing}}", state) == ""


def test_resolve_reference_whitespace_tolerance():
    state: WorkflowState = {"inputs": {"name": "test"}}
    assert resolve_reference("{{ name }}", state) == "test"
    assert resolve_reference("{{  name  }}", state) == "test"


def test_render_template_simple():
    state: WorkflowState = {
        "node_outputs": {
            "llm_1": {"text": "Generated script"},
            "tts_1": {"audio_url": "/audio/1.mp3"},
        }
    }
    template = "Audio: {{tts_1.audio_url}}, Text: {{llm_1.text}}"
    assert render_template(template, state) == "Audio: /audio/1.mp3, Text: Generated script"


def test_render_template_with_local_vars():
    state: WorkflowState = {
        "node_outputs": {"tts_1": {"audio_url": "/audio/1.mp3"}},
    }
    local_vars = {"title": "My Podcast"}
    template = "{{title}}: {{tts_1.audio_url}}"
    assert render_template(template, state, local_vars) == "My Podcast: /audio/1.mp3"


def test_render_template_unmatched_refs_become_empty():
    state: WorkflowState = {"node_outputs": {}}
    template = "Hello {{missing}}, link: {{missing.link}}"
    assert render_template(template, state) == "Hello , link: "


def test_render_template_literal_preserved():
    state: WorkflowState = {"node_outputs": {}}
    template = "No placeholders here!"
    assert render_template(template, state) == "No placeholders here!"


def test_render_template_number_values():
    state: WorkflowState = {
        "node_outputs": {"calc_1": {"value": 42}},
    }
    template = "Result: {{calc_1.value}}"
    assert render_template(template, state) == "Result: 42"


def test_render_template_none_value_becomes_empty():
    state: WorkflowState = {
        "node_outputs": {"node_1": {"field": None}},
    }
    template = "Value: {{node_1.field}}"
    assert render_template(template, state) == "Value: "
