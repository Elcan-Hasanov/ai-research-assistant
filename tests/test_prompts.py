import pytest

from app.prompts.registry import (
    PromptLoadError,
    PromptRenderError,
    load_templates,
    render,
    render_template,
)


def test_missing_user_section_raises_error(tmp_path):
    """A template file without a 'user' section violates the file contract."""
    (tmp_path / "summarize.v1.txt").write_text(
        "--- system ---\nSome system prompt", encoding="utf-8"
    )

    with pytest.raises(PromptLoadError, match="missing required section 'user'"):
        load_templates(tmp_path)


def test_invalid_filename_raises_error(tmp_path):
    """A filename without a version is a load error, not a skipped file."""
    (tmp_path / "summarize.txt").write_text("--- user ---\nHello", encoding="utf-8")

    with pytest.raises(PromptLoadError, match="filename does not match"):
        load_templates(tmp_path)


def test_missing_variable_raises_error():
    """A declared variable the caller did not supply is an error, not a blank."""
    with pytest.raises(PromptRenderError, match=r"missing=\['abstract'\]"):
        render("summarize_article.v1", title="Test")


def test_unexpected_variable_raises_error():
    """A variable the template never declared is an error, not silently dropped."""
    with pytest.raises(PromptRenderError, match=r"unexpected=\['extra_param'\]"):
        render(
            "summarize_article.v1",
            title="Test",
            abstract="Abstract",
            extra_param="invalid",
        )


def test_literal_json_braces_survive_rendering(tmp_path):
    """Literal braces are content, not placeholders. This is why Jinja2 was chosen."""
    (tmp_path / "json_schema.v1.txt").write_text(
        '--- user ---\nExtract {{ topic }} using schema: {"status": "ok", "count": 1}',
        encoding="utf-8",
    )

    templates = load_templates(tmp_path)
    rendered = render_template(templates["json_schema.v1"], {"topic": "AI"})

    assert rendered.user == 'Extract AI using schema: {"status": "ok", "count": 1}'


def test_template_without_system_section_renders_none(tmp_path):
    """An absent system section becomes None, matching complete(system=None)."""
    (tmp_path / "user_only.v1.txt").write_text(
        "--- user ---\nHello {{ name }}", encoding="utf-8"
    )

    templates = load_templates(tmp_path)
    rendered = render_template(templates["user_only.v1"], {"name": "World"})

    assert rendered.user == "Hello World"
    assert rendered.system is None


def test_render_success():
    """The happy path: both sections render, and they stay separate."""
    rendered = render("summarize_article.v1", title="Title", abstract="Abstract")

    assert "Title" in rendered.user
    assert "Abstract" in rendered.user
    assert rendered.system is not None
    assert "Title" not in rendered.system