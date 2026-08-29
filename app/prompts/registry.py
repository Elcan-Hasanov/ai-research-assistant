"""Prompt template loading and rendering.

Templates live on disk as versioned .txt files. This module is a leaf:
it imports nothing else from this application.
"""

import re
from pathlib import Path

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, meta
from jinja2.exceptions import UndefinedError
from pydantic import BaseModel

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_FILENAME_RE = re.compile(r"^(?P<name>[a-z0-9_]+)\.v(?P<version>\d+)$")
_MARKER_RE = re.compile(r"^---\s*(?P<section>[a-z]+)\s*---$")
_SECTIONS = ("system", "user")


class PromptError(Exception):
    """Base for every failure raised by this module."""


class PromptLoadError(PromptError):
    """A template on disk violates the file contract."""


class PromptRenderError(PromptError):
    """A caller asked for a prompt this module cannot produce."""


class PromptTemplate(BaseModel):
    """One versioned template, parsed and ready to render."""

    name: str
    version: int
    system: str | None
    user: str
    variables: frozenset[str]

    @property
    def identifier(self) -> str:
        return f"{self.name}.v{self.version}"


class RenderedPrompt(BaseModel):
    """Exactly the two pieces LLMClient.complete() accepts."""

    system: str | None
    user: str


_env = Environment(undefined=StrictUndefined)


def _split_sections(text: str, source: str) -> dict[str, str]:
    """Split one template file into its named sections."""
    collected: dict[str, list[str]] = {}
    current: str | None = None

    for line in text.splitlines():
        marker = _MARKER_RE.match(line.strip())

        if marker is not None:
            section = marker.group("section")
            
            if section not in _SECTIONS:
                raise PromptLoadError(f"{source}: unknown section '{section}'")
            if section in collected:
                raise PromptLoadError(f"{source}: duplicate section '{section}'")
            collected[section] = []
            current = section
            continue

        if current is None:
            if line.strip():
                raise PromptLoadError(
                    f"{source}: content before the first section marker"
                )
            continue

        collected[current].append(line)

    sections = {name: "\n".join(lines).strip() for name, lines in collected.items()}

    if "user" not in sections:
        raise PromptLoadError(f"{source}: missing required section 'user'")

    for name, body in sections.items():
        if not body:
            raise PromptLoadError(f"{source}: section '{name}' is empty")

    return sections


def _declared_variables(sections: dict[str, str], source: str) -> frozenset[str]:
    """Collect the variable names the template itself declares."""
    found: set[str] = set()

    for name, body in sections.items():
        try:
            found |= meta.find_undeclared_variables(_env.parse(body))
        except TemplateSyntaxError as exc:
            raise PromptLoadError(
                f"{source}: syntax error in section '{name}' at line {exc.lineno}"
            ) from exc

    return frozenset(found)


def load_templates(directory: Path = TEMPLATES_DIR) -> dict[str, PromptTemplate]:
    """Read every template in a directory. Raises on the first bad file."""
    if not directory.is_dir(): 
        raise PromptLoadError(f"Template directory not found: {directory}")

    templates: dict[str, PromptTemplate] = {}

    for path in sorted(directory.glob("*.txt")):
        filename = _FILENAME_RE.match(path.stem)
        if filename is None:
            raise PromptLoadError(
                f"{path.name}: filename does not match '<name>.v<N>.txt'"
            )

        sections = _split_sections(path.read_text(encoding="utf-8"), path.name)

        template = PromptTemplate(
            name=filename.group("name"),
            version=int(filename.group("version")),
            system=sections.get("system"),
            user=sections["user"],
            variables=_declared_variables(sections, path.name),
        )
        templates[template.identifier] = template

    return templates


_TEMPLATES: dict[str, PromptTemplate] = load_templates()


def render_template(
    template: PromptTemplate, variables: dict[str, object]
) -> RenderedPrompt:
    """Render an already-loaded template. Touches no disk, looks nothing up."""
    given = frozenset(variables)
    missing = template.variables - given
    unexpected = given - template.variables

    if missing or unexpected:
        raise PromptRenderError(
            f"{template.identifier}: variable mismatch — "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )

    try:
        system = (
            None
            if template.system is None
            else _env.from_string(template.system).render(**variables)
        )
        user = _env.from_string(template.user).render(**variables)
    except UndefinedError as exc:
        raise PromptRenderError(
            f"{template.identifier}: undefined value during render"
        ) from exc

    return RenderedPrompt(system=system, user=user)


def render(identifier: str, /, **variables: object) -> RenderedPrompt:
    """Look up a prompt by identifier and render it."""
    template = _TEMPLATES.get(identifier)

    if template is None:
        raise PromptRenderError(
            f"Unknown prompt '{identifier}'. Loaded: {sorted(_TEMPLATES)}"
        )

    return render_template(template, variables)