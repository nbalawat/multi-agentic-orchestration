"""
Workflow Runner

Executes guided workflow templates for RAP convergence phases.
Templates are section-based, interactive documents that are filled
iteratively through AI-human conversation.
"""

import uuid
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class WorkflowSection(BaseModel):
    """A single section in a guided workflow."""

    index: int
    title: str
    guide: str  # The prompt/guide text for this section
    content: Optional[str] = None  # Filled content
    status: str = "pending"  # pending, in_progress, complete, skipped
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class WorkflowTemplate(BaseModel):
    """A guided workflow template for a RAPIDS phase."""

    id: str
    phase: str
    archetype: str
    title: str
    description: Optional[str] = None
    sections: List[WorkflowSection] = Field(default_factory=list)
    status: str = "not_started"  # not_started, in_progress, complete
    output_artifacts: List[str] = Field(default_factory=list)  # Expected artifact filenames
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# Default output artifacts per phase
_DEFAULT_ARTIFACTS: Dict[str, List[str]] = {
    "research": ["findings.md", "context.md"],
    "analysis": ["solution.md", "architecture.md"],
    "plan": ["spec.md"],
}


class WorkflowRunner:
    """Executes guided workflow templates for RAP convergence phases."""

    def __init__(self, plugins_dir: Path):
        self._plugins_dir = plugins_dir
        self._active_workflows: Dict[str, WorkflowTemplate] = {}

    # =========================================================================
    # Template loading
    # =========================================================================

    def load_workflow_template(
        self, plugin_name: str, phase: str
    ) -> Optional[WorkflowTemplate]:
        """
        Load a workflow template from a plugin's workflows/ directory.
        Parses the markdown file into sections.

        Expected path: <plugins_dir>/<plugin_name>/workflows/<phase>.md

        Expected format of workflow .md file:
        ```
        # Research Workflow -- Greenfield Archetype

        Description text here.

        ## Section 1: Problem Statement
        > Guide: Describe the problem this project solves.

        ## Section 2: Technology Landscape
        > Guide: What technologies are relevant?
        ```
        """
        workflow_dir = self._plugins_dir / plugin_name / "workflows"
        # Try both naming conventions: <phase>-workflow.md and <phase>.md
        workflow_file = workflow_dir / f"{phase}-workflow.md"
        if not workflow_file.exists():
            workflow_file = workflow_dir / f"{phase}.md"

        if not workflow_file.exists():
            return None

        try:
            content = workflow_file.read_text(encoding="utf-8")
        except OSError:
            return None

        return self._parse_workflow_markdown(content, phase, plugin_name)

    def _parse_workflow_markdown(
        self, content: str, phase: str, plugin_name: str
    ) -> WorkflowTemplate:
        """Parse a workflow markdown file into a WorkflowTemplate."""
        lines = content.split("\n")

        # Extract title from first H1 heading
        title = f"{phase.capitalize()} Workflow"
        description_lines: List[str] = []
        sections: List[WorkflowSection] = []

        # State machine for parsing
        in_description = False
        current_section_title: Optional[str] = None
        current_section_index = -1
        current_guide_lines: List[str] = []

        for line in lines:
            stripped = line.strip()

            # H1 heading -> workflow title
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = stripped[2:].strip()
                in_description = True
                continue

            # H2 heading -> new section
            # Supports: "## Section 1: Title", "## 1. Title", "## 1: Title"
            section_match = re.match(
                r"^##\s+(?:Section\s+)?(\d+)[\.\:]\s*(.+)$", stripped, re.IGNORECASE
            )
            if section_match:
                # Finalize previous section if any
                if current_section_title is not None:
                    guide_text = "\n".join(current_guide_lines).strip()
                    sections.append(
                        WorkflowSection(
                            index=current_section_index,
                            title=current_section_title,
                            guide=guide_text,
                        )
                    )

                current_section_index = int(section_match.group(1)) - 1
                current_section_title = section_match.group(2).strip()
                current_guide_lines = []
                in_description = False
                continue

            # Skip horizontal rules (---) used as separators
            if stripped == '---':
                continue

            # Guide line inside a section
            if current_section_title is not None:
                guide_match = re.match(r"^>\s*Guide\s*:\s*(.+)$", stripped, re.IGNORECASE)
                if guide_match:
                    current_guide_lines.append(guide_match.group(1).strip())
                elif stripped.startswith("> "):
                    # Continuation of a blockquote guide
                    current_guide_lines.append(stripped[2:].strip())
                elif stripped:
                    # Regular content line within a section (additional guide text)
                    current_guide_lines.append(stripped)
                continue

            # Description text (between title and first section)
            if in_description and stripped:
                description_lines.append(stripped)

        # Finalize the last section
        if current_section_title is not None:
            guide_text = "\n".join(current_guide_lines).strip()
            sections.append(
                WorkflowSection(
                    index=current_section_index,
                    title=current_section_title,
                    guide=guide_text,
                )
            )

        # Re-index sections sequentially in case of gaps
        for i, section in enumerate(sections):
            section.index = i

        description = "\n".join(description_lines).strip() or None
        output_artifacts = _DEFAULT_ARTIFACTS.get(phase, [])

        workflow_id = str(uuid.uuid4())

        return WorkflowTemplate(
            id=workflow_id,
            phase=phase,
            archetype=plugin_name,
            title=title,
            description=description,
            sections=sections,
            output_artifacts=list(output_artifacts),
        )

    # =========================================================================
    # Workflow lifecycle
    # =========================================================================

    def start_workflow(self, workflow: WorkflowTemplate) -> str:
        """Start a workflow. Returns the workflow ID."""
        now = datetime.now(timezone.utc).isoformat()
        workflow.status = "in_progress"
        workflow.started_at = now
        self._active_workflows[workflow.id] = workflow
        return workflow.id

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowTemplate]:
        """Get an active workflow by ID."""
        return self._active_workflows.get(workflow_id)

    def get_current_section(self, workflow_id: str) -> Optional[WorkflowSection]:
        """Get the current (first non-complete, non-skipped) section."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return None

        for section in workflow.sections:
            if section.status in ("pending", "in_progress"):
                return section
        return None

    # =========================================================================
    # Section operations
    # =========================================================================

    def start_section(self, workflow_id: str, section_index: int) -> Optional[Dict]:
        """Start a section. Returns section info with guide text."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return None

        section = self._get_section(workflow, section_index)
        if section is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        section.status = "in_progress"
        section.started_at = now

        return {
            "index": section.index,
            "title": section.title,
            "guide": section.guide,
            "status": section.status,
            "started_at": section.started_at,
        }

    def complete_section(
        self, workflow_id: str, section_index: int, content: str
    ) -> Optional[Dict]:
        """Complete a section with content. Returns updated section."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return None

        section = self._get_section(workflow, section_index)
        if section is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        section.status = "complete"
        section.content = content
        section.completed_at = now

        # If section wasn't started yet, set started_at as well
        if section.started_at is None:
            section.started_at = now

        return {
            "index": section.index,
            "title": section.title,
            "status": section.status,
            "content": section.content,
            "started_at": section.started_at,
            "completed_at": section.completed_at,
        }

    def skip_section(self, workflow_id: str, section_index: int) -> Optional[Dict]:
        """Skip a section."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return None

        section = self._get_section(workflow, section_index)
        if section is None:
            return None

        now = datetime.now(timezone.utc).isoformat()
        section.status = "skipped"
        section.completed_at = now

        return {
            "index": section.index,
            "title": section.title,
            "status": section.status,
            "completed_at": section.completed_at,
        }

    # =========================================================================
    # Progress and finalization
    # =========================================================================

    def get_progress(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow progress summary."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return None

        total = len(workflow.sections)
        completed = sum(1 for s in workflow.sections if s.status == "complete")
        skipped = sum(1 for s in workflow.sections if s.status == "skipped")
        in_progress = sum(1 for s in workflow.sections if s.status == "in_progress")
        pending = sum(1 for s in workflow.sections if s.status == "pending")

        return {
            "workflow_id": workflow.id,
            "title": workflow.title,
            "phase": workflow.phase,
            "status": workflow.status,
            "total_sections": total,
            "completed": completed,
            "skipped": skipped,
            "in_progress": in_progress,
            "pending": pending,
            "percent_complete": round((completed + skipped) / total * 100, 1) if total > 0 else 0.0,
        }

    def is_complete(self, workflow_id: str) -> bool:
        """Check if all sections are complete or skipped."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return False

        if len(workflow.sections) == 0:
            return False

        return all(
            s.status in ("complete", "skipped") for s in workflow.sections
        )

    def finalize_workflow(self, workflow_id: str) -> Optional[Dict]:
        """
        Finalize a workflow:
        1. Mark workflow as complete
        2. Compile all section content into output artifacts
        3. Return artifact content map
        """
        workflow = self._active_workflows.get(workflow_id)
        if workflow is None:
            return None

        if not self.is_complete(workflow_id):
            incomplete = [
                s.title
                for s in workflow.sections
                if s.status not in ("complete", "skipped")
            ]
            return {
                "error": "Workflow not complete",
                "incomplete_sections": incomplete,
            }

        now = datetime.now(timezone.utc).isoformat()
        workflow.status = "complete"
        workflow.completed_at = now

        artifacts = self.compile_artifacts(workflow)

        return {
            "workflow_id": workflow.id,
            "title": workflow.title,
            "phase": workflow.phase,
            "status": workflow.status,
            "completed_at": now,
            "artifacts": artifacts,
        }

    def compile_artifacts(self, workflow: WorkflowTemplate) -> Dict[str, str]:
        """
        Compile workflow sections into output artifacts.
        For research: findings.md and context.md
        For analysis: solution.md and architecture.md
        For plan: spec.md outline
        Returns {filename: content}
        """
        # Collect all completed section content
        completed_sections = [
            s for s in workflow.sections if s.status == "complete" and s.content
        ]

        if not completed_sections:
            return {}

        phase = workflow.phase

        if phase == "research":
            return self._compile_research_artifacts(workflow, completed_sections)
        elif phase == "analysis":
            return self._compile_analysis_artifacts(workflow, completed_sections)
        elif phase == "plan":
            return self._compile_plan_artifacts(workflow, completed_sections)
        else:
            # Generic: combine all sections into a single document
            return self._compile_generic_artifacts(workflow, completed_sections)

    def list_active_workflows(self) -> List[Dict]:
        """List all active workflows."""
        result = []
        for wf in self._active_workflows.values():
            total = len(wf.sections)
            completed = sum(1 for s in wf.sections if s.status in ("complete", "skipped"))
            result.append({
                "id": wf.id,
                "phase": wf.phase,
                "archetype": wf.archetype,
                "title": wf.title,
                "status": wf.status,
                "total_sections": total,
                "completed_sections": completed,
                "started_at": wf.started_at,
            })
        return result

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _get_section(
        self, workflow: WorkflowTemplate, section_index: int
    ) -> Optional[WorkflowSection]:
        """Get a section by index from a workflow."""
        for section in workflow.sections:
            if section.index == section_index:
                return section
        return None

    def _compile_research_artifacts(
        self,
        workflow: WorkflowTemplate,
        sections: List[WorkflowSection],
    ) -> Dict[str, str]:
        """Compile research phase artifacts: findings.md and context.md."""
        # Split sections: first half -> findings, second half -> context
        mid = max(1, len(sections) // 2)
        findings_sections = sections[:mid]
        context_sections = sections[mid:]

        findings_content = self._format_artifact(
            f"# Research Findings -- {workflow.title}",
            findings_sections,
        )

        context_content = self._format_artifact(
            f"# Research Context -- {workflow.title}",
            context_sections if context_sections else findings_sections,
        )

        return {
            "findings.md": findings_content,
            "context.md": context_content,
        }

    def _compile_analysis_artifacts(
        self,
        workflow: WorkflowTemplate,
        sections: List[WorkflowSection],
    ) -> Dict[str, str]:
        """Compile analysis phase artifacts: solution.md and architecture.md."""
        mid = max(1, len(sections) // 2)
        solution_sections = sections[:mid]
        architecture_sections = sections[mid:]

        solution_content = self._format_artifact(
            f"# Solution Analysis -- {workflow.title}",
            solution_sections,
        )

        architecture_content = self._format_artifact(
            f"# Architecture -- {workflow.title}",
            architecture_sections if architecture_sections else solution_sections,
        )

        return {
            "solution.md": solution_content,
            "architecture.md": architecture_content,
        }

    def _compile_plan_artifacts(
        self,
        workflow: WorkflowTemplate,
        sections: List[WorkflowSection],
    ) -> Dict[str, str]:
        """Compile plan phase artifacts: spec.md."""
        spec_content = self._format_artifact(
            f"# Specification -- {workflow.title}",
            sections,
        )

        return {
            "spec.md": spec_content,
        }

    def _compile_generic_artifacts(
        self,
        workflow: WorkflowTemplate,
        sections: List[WorkflowSection],
    ) -> Dict[str, str]:
        """Compile a generic artifact for phases without specific templates."""
        content = self._format_artifact(
            f"# {workflow.phase.capitalize()} -- {workflow.title}",
            sections,
        )

        filename = f"{workflow.phase}.md"
        return {filename: content}

    def _format_artifact(
        self, heading: str, sections: List[WorkflowSection]
    ) -> str:
        """Format sections into a markdown document."""
        parts = [heading, ""]

        for section in sections:
            parts.append(f"## {section.title}")
            parts.append("")
            if section.content:
                parts.append(section.content)
            parts.append("")

        now = datetime.now(timezone.utc).isoformat()
        parts.append(f"---\n*Generated at {now}*")
        return "\n".join(parts)
