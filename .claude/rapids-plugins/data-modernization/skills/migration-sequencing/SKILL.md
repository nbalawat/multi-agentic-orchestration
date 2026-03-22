---
description: Sequence migration steps with dependency ordering and rollback planning. Use when planning data migrations.
allowed-tools: Read, Grep, Glob, Write, Edit, Bash
---

Create a dependency-ordered sequence of migration steps. Each step must include: forward migration script, rollback script, validation queries, and data integrity checks. Build a feature DAG for the migration.
