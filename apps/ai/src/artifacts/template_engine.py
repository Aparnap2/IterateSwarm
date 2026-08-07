"""V6 OntologyAI — Jinja2 Template Engine.

Per §6 (ADR-012 / ADR-002) of the V6 spec, all artifact generation is
template-driven.  Every artifact section is rendered by a Jinja2 template
that receives structured data from the canonical model plus optional LLM
narrative.

Templates are sandboxed (no arbitrary Python execution) via Jinja2's
``SandboxedEnvironment``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from jinja2 import BaseLoader, Environment, FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from src.artifacts.dsl_loader import ArtifactDSL, ArtifactSection

logger = logging.getLogger(__name__)


# ── Exceptions ──────────────────────────────────────────────────────────


class TemplateRenderError(Exception):
    """Raised when a template fails to render."""


# ── Default template directory ──────────────────────────────────────────


def _default_template_dir() -> str:
    """Return the default path to the artifact templates directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "templates")


# ── Built-in section templates (used when no file template exists) ──────


_BUILTIN_TEMPLATES: dict[str, str] = {
    "title": "{{ data | default('Untitled', true) }}\n",
    "summary": "{{ data | default('No summary available.', true) }}\n",
    "evidence_list": (
        "{% if data %}\n"
        "{% for item in data %}\n"
        "- [{{ item.confidence | default('?', true) }}] {{ item.source | default('Unknown', true) }}"
        "{% if item.structured_data %}: {{ item.structured_data }}{% endif %}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No evidence records to display.\n"
        "{% endif %}\n"
    ),
    "decision_table": (
        "{% if data %}\n"
        "| Decision | Status | Owner |\n"
        "|----------|--------|-------|\n"
        "{% for d in data %}\n"
        "| {{ d.title | default('Untitled', true) }}"
        " | {{ d.status | default('unknown', true) }}"
        " | {{ d.owner_id | default('-', true) }} |\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No active decisions.\n"
        "{% endif %}\n"
    ),
    "recommendation_list": (
        "{% if data %}\n"
        "{% for rec in data %}\n"
        "1. **{{ rec.option_title | default('Option', true) }}**"
        " — {{ rec.justification | default('No justification.', true) }}"
        " (confidence: {{ rec.confidence | default('N/A', true) }})\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No recommendations available.\n"
        "{% endif %}\n"
    ),
    "risk_matrix": (
        "{% if data %}\n"
        "| Risk | Severity | Probability | Status |\n"
        "|------|----------|-------------|--------|\n"
        "{% for r in data %}\n"
        "| {{ r.description | default('Risk', true) }}"
        " | {{ r.severity | default('?', true) }}"
        " | {{ r.probability | default('?', true) }}"
        " | {{ r.status | default('identified', true) }} |\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No risks identified.\n"
        "{% endif %}\n"
    ),
    "impact_analysis": (
        "{% if data %}\n"
        "{% for impact in data %}\n"
        "- **{{ impact.entity_type | default('Entity', true) }}**"
        " ({{ impact.entity_id | default('?', true) }}): "
        "{{ impact.impact_type | default('neutral', true) }}"
        " — magnitude {{ impact.magnitude | default(0, true) }}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No downstream impact data available.\n"
        "{% endif %}\n"
    ),
    "kpi_table": (
        "{% if data %}\n"
        "| KPI | Baseline | Target | Current | Unit |\n"
        "|-----|----------|--------|---------|------|\n"
        "{% for k in data %}\n"
        "| {{ k.name | default('KPI', true) }}"
        " | {{ k.baseline_value | default('-', true) }}"
        " | {{ k.target_value | default('-', true) }}"
        " | {{ k.current_value | default('-', true) }}"
        " | {{ k.unit | default('', true) }} |\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No KPI data available.\n"
        "{% endif %}\n"
    ),
    "stakeholder_table": (
        "{% if data %}\n"
        "| Name | Role | Status |\n"
        "|------|------|--------|\n"
        "{% for s in data %}\n"
        "| {{ s.name | default('Unknown', true) }}"
        " | {{ s.role | default('-', true) }}"
        " | {{ s.status | default('identified', true) }} |\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No stakeholder data available.\n"
        "{% endif %}\n"
    ),
    "table": (
        "{% if data %}\n"
        "{% if data is mapping %}\n"
        "{{ data }}\n"
        "{% elif data is iterable and data is not string %}\n"
        "{% for row in data %}\n"
        "- {{ row }}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "{{ data }}\n"
        "{% endif %}\n"
        "{% else %}\n"
        "No data available.\n"
        "{% endif %}\n"
    ),
    "list": (
        "{% if data %}\n"
        "{% if data is iterable and data is not string %}\n"
        "{% for item in data %}\n"
        "- {{ item }}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "- {{ data }}\n"
        "{% endif %}\n"
        "{% else %}\n"
        "No items to display.\n"
        "{% endif %}\n"
    ),
    "narrative": (
        "{% if data %}\n"
        "{{ data }}\n"
        "{% else %}\n"
        "Narrative content not yet available.\n"
        "{% endif %}\n"
    ),
    "timeline": (
        "{% if data %}\n"
        "{% for item in data %}\n"
        "- {{ item.date | default('?', true) }}: "
        "{{ item.event | default(item, true) }}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No timeline data available.\n"
        "{% endif %}\n"
    ),
    "gantt": (
        "{% if data %}\n"
        "{% for task in data %}\n"
        "- **{{ task.name | default('Task', true) }}**: "
        "{{ task.start | default('?', true) }} → "
        "{{ task.end | default('?', true) }}"
        "{% if task.owner %} ({{ task.owner }}){% endif %}\n"
        "{% endfor %}\n"
        "{% else %}\n"
        "No Gantt data available.\n"
        "{% endif %}\n"
    ),
    "diagram_placeholder": (
        "[Diagram placeholder: {{ section_name | default('Diagram', true) }}"
        " — type: {{ config.diagram_type | default('generic', true) }}]\n"
    ),
}


# ── TemplateEngine ──────────────────────────────────────────────────────


class TemplateEngine:
    """Jinja2-based template renderer for artifact sections.

    Templates are sandboxed via ``SandboxedEnvironment`` (no arbitrary
    Python execution).  Each section type has a corresponding template
    loaded from the filesystem or from built-in defaults.

    The render context passed to every template includes:

    * ``data`` — the raw data extracted from the canonical model
    * ``section_name`` — the section's display name
    * ``config`` — the section's config dict
    * ``dsl`` — the parent ``ArtifactDSL`` instance
    """

    def __init__(self, template_dir: str | None = None) -> None:
        """Initialise the template engine.

        Parameters
        ----------
        template_dir:
            Path to the directory containing Jinja2 template files
            (``*.j2``).  If ``None``, defaults to
            ``apps/ai/src/artifacts/templates/``.  Falls back to built-in
            string templates when no file is found.
        """
        template_dir = template_dir or _default_template_dir()
        self._template_dir = template_dir

        loader: BaseLoader
        if os.path.isdir(template_dir):
            loader = FileSystemLoader(template_dir)
            logger.info("Template engine using directory: %s", template_dir)
        else:
            loader = _BuiltinLoader()
            logger.info(
                "Template directory %s not found — using built-in templates.",
                template_dir,
            )

        self._env: Environment = SandboxedEnvironment(
            loader=loader,
            undefined=StrictUndefined,
            autoescape=False,  # artifacts are not HTML
        )

    # ── Public API ───────────────────────────────────────────────────

    def render_section(
        self,
        section: ArtifactSection,
        context: dict[str, Any],
        dsl: ArtifactDSL | None = None,
    ) -> str:
        """Render a single artifact section from template + context data.

        Parameters
        ----------
        section:
            The section definition from the DSL config.
        context:
            Data context — must include ``data`` as the value extracted
            from the canonical model.
        dsl:
            Optional parent ``ArtifactDSL`` — passed into the template
            context as ``dsl``.

        Returns
        -------
        str
            The rendered section content.

        Raises
        ------
        TemplateRenderError
            If rendering fails (undefined variable, syntax error, etc.).
        """
        template_name = f"{section.type}.j2"
        render_context: dict[str, Any] = {
            "data": context.get("data"),
            "section_name": section.name,
            "config": section.config,
            "dsl": dsl.model_dump() if dsl else None,
            **context,
        }

        try:
            # Try to load a file template first; fall back to built-in name
            try:
                tmpl = self._env.get_template(template_name)
            except Exception:
                # Fallback: load built-in template for this type
                builtin_source = _BUILTIN_TEMPLATES.get(section.type)
                if builtin_source is None:
                    raise TemplateRenderError(
                        f"No template found for section type '{section.type}'. "
                        f"Create a template file named '{template_name}' or "
                        f"register a built-in template for this type."
                    ) from None
                tmpl = self._env.from_string(builtin_source)

            rendered = tmpl.render(**render_context)
            return rendered.strip() + "\n"

        except Exception as exc:
            raise TemplateRenderError(
                f"Failed to render section '{section.name}' (type={section.type}): {exc}"
            ) from exc

    def render_artifact(
        self,
        dsl: ArtifactDSL,
        context: dict[str, Any],
    ) -> dict[str, str]:
        """Render all sections of an artifact.

        Parameters
        ----------
        dsl:
            The artifact DSL config.
        context:
            Data context — a dict mapping ``section.source`` dot-paths to
            their extracted canonical model values.  E.g.::

                {
                    "workspace.title": "Acme Corp Strategy Review",
                    "evidence.top_findings": [...],
                    ...
                }

        Returns
        -------
        dict[str, str]
            A dict mapping section ``name`` → rendered content string.
        """
        result: dict[str, str] = {}

        for section in dsl.sections:
            # Extract data for this section's source path from context
            section_data = _resolve_dot_path(context, section.source)
            render_ctx: dict[str, Any] = {
                "data": section_data,
            }

            try:
                rendered = self.render_section(section, render_ctx, dsl=dsl)
                result[section.name] = rendered
            except TemplateRenderError as exc:
                logger.error(
                    "Failed to render section '%s' for artifact '%s': %s",
                    section.name,
                    dsl.id,
                    exc,
                )
                result[section.name] = (
                    f"[Error rendering section '{section.name}': {exc}]\n"
                )

        return result


# ── Helpers ─────────────────────────────────────────────────────────────


def _resolve_dot_path(context: dict[str, Any], dot_path: str) -> Any:
    """Resolve a dot-separated path against a nested dict.

    E.g. ``_resolve_dot_path({"a": {"b": 1}}, "a.b")`` → ``1``.
    Returns ``None`` for any missing key segment.
    """
    keys = dot_path.split(".")
    current: Any = context
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


class _BuiltinLoader(BaseLoader):
    """Jinja2 loader that returns built-in templates by type name.

    This loader is used when no template directory exists.  It maps
    ``"<type>.j2"`` → ``_BUILTIN_TEMPLATES[<type>]``.
    """

    def get_source(
        self,
        environment: Environment,
        template: str,
    ) -> tuple[str, str | None, callable | None]:
        """Resolve a template name to its built-in source.

        Parameters
        ----------
        environment:
            The Jinja2 environment (unused).
        template:
            Template name like ``"summary.j2"``.

        Returns
        -------
        tuple[str, str | None, callable | None]
            ``(source, filename, uptodate_func)``.

        Raises
        ------
        TemplateNotFound
            If no built-in template exists for this name.
        """
        from jinja2 import TemplateNotFound

        stem = template.rsplit(".", 1)[0] if "." in template else template
        source = _BUILTIN_TEMPLATES.get(stem)
        if source is None:
            raise TemplateNotFound(template)
        return source, f"<builtin:{stem}>", None

    def list_templates(self) -> list[str]:
        return [f"{name}.j2" for name in _BUILTIN_TEMPLATES]
