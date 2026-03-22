# Research Workflow — Greenfield Archetype

Guided workflow for the Research phase of a greenfield project. The goal is to build a comprehensive understanding of the problem space before any design or implementation decisions are made.

---

## 1. Problem Statement

Define the core problem this project will solve.

**Activities:**
- Interview stakeholders (or review provided requirements) to understand the business need
- Write a clear, concise problem statement (1-2 paragraphs)
- Identify the target users and their pain points
- Define success metrics and measurable outcomes
- Document what is explicitly out of scope

**Artifacts:**
- `.rapids/research/problem-statement.md` — The canonical problem definition
- `.rapids/research/success-metrics.md` — Quantifiable success criteria

**Exit check:** Problem statement reviewed and confirmed by user.

---

## 2. Technology Landscape

Survey available technologies, frameworks, and platforms relevant to the problem domain.

**Activities:**
- Identify the major technology categories required (language, framework, database, hosting, etc.)
- For each category, list 2-4 viable options with pros/cons
- Research community health, documentation quality, and long-term viability of each option
- Evaluate compatibility between candidate technologies
- Note any licensing constraints or cost implications

**Artifacts:**
- `.rapids/research/technology-landscape.md` — Survey of options per category with comparative analysis

**Exit check:** All major technology categories have at least two evaluated options.

---

## 3. Constraints & Requirements

Enumerate all technical, business, and operational constraints that will shape the solution.

**Activities:**
- Document hard technical constraints (platform, language mandates, integration requirements)
- Identify performance requirements (latency, throughput, availability targets)
- Capture security and compliance requirements (authentication, data handling, regulations)
- Note budget and timeline constraints
- Document team skill constraints and learning curve considerations
- List all external system integrations required

**Artifacts:**
- `.rapids/research/constraints.md` — Categorized constraint register
- `.rapids/research/requirements.md` — Functional and non-functional requirements list

**Exit check:** Constraints reviewed with stakeholders; no known gaps.

---

## 4. Domain Context

Build understanding of the domain in which the project operates.

**Activities:**
- Define key domain terms and concepts (ubiquitous language)
- Map the major domain entities and their relationships
- Identify existing workflows that the system must support or improve
- Research industry standards, protocols, or conventions applicable to this domain
- Document any regulatory or compliance frameworks relevant to the domain

**Artifacts:**
- `.rapids/research/domain-glossary.md` — Key terms and definitions
- `.rapids/research/domain-model.md` — High-level entity relationship description

**Exit check:** Domain model covers all entities referenced in the problem statement.

---

## 5. Stakeholders & Communication

Identify all stakeholders and establish communication patterns.

**Activities:**
- List all stakeholders (users, sponsors, operators, integrators)
- Document each stakeholder's primary concerns and success criteria
- Identify decision makers for key technical and product choices
- Establish feedback loops and review cadences
- Document any organizational constraints (team structure, approval processes)

**Artifacts:**
- `.rapids/research/stakeholders.md` — Stakeholder register with roles and concerns

**Exit check:** All stakeholder groups identified and their requirements captured.

---

## Phase Completion

The Research phase is complete when:
1. Problem statement is defined and confirmed
2. Technology landscape is documented with viable options
3. All constraints and requirements are captured
4. Domain context is established with glossary and entity model
5. Stakeholders are identified with their concerns documented

All artifacts should be written to `.rapids/research/` and committed to version control.
