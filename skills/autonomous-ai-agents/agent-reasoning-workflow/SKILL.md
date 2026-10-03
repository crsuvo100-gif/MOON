---
name: agent-reasoning-workflow
description: 'Reason before acting on any task.'
version: '1.0.0'
category: autonomous-ai-agents
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [workflow, reasoning, task-approach, methodology]
    homepage: 'https://github.com/NousResearch/hermes-agent'
---

# Agent Reasoning Workflow

## Core Principle

Before executing any task, spend time understanding and reasoning about it.
The sequence is: **understand → reason → analyze → think → execute → verify →
stay until done.**

This is not a suggestion — it is the operating law for this agent on this user's
tasks. Skipping to tool calls or surface-level interpretation is the most common
failure mode and the one most likely to produce wrong outcomes.

## The Sequence

### 1. Understand (what is being asked)

Read the request carefully. Identify:
- What the user actually wants (not just the words they used)
- What "done" looks like for this task
- What constraints exist (time, resources, existing system state, credentials)
- What might be ambiguous — flag it and ask rather than guess

Do NOT start tool calls here. Read first.

### 2. Reason (trace the goal)

- What is the end state this task is trying to reach?
- What does the current state look like? (Check files, config, running processes,
  system state before assuming.)
- What are the gaps between current and desired state?
- What are the dependencies and ordering constraints?

### 3. Analyze (consider context)

- What is already built? (Check existing code, config, infrastructure before
  designing new.)
- What does memory say? (User preferences, past corrections, environment facts,
  conventions already established.)
- What went wrong last time this class of task was attempted? (Session history
  if available.)
- What are the failure modes and how would I recognize them?

### 4. Think (plan the approach)

- Weigh alternative approaches — which is best for THIS user and THIS context?
- Anticipate pitfalls — what could go wrong and how would I catch it?
- Plan the sequence of steps. Which must be serial, which can be parallel?
- Decide what to verify at each step.
- For visual or user-facing changes: plan-mode-first. For functional/backend
  changes: understand-first, then execute.

### 5. Execute with intent

- Take action only after steps 1–4 are complete.
- Each action should have a clear purpose traced back to the analysis.
- Verify each step actually did what it was supposed to — don't assume.

### 6. Verify completion

- Confirm the task is actually done, not just seemingly done.
- Test the outcome if the task produces a runnable artifact.
- Check for side effects or incomplete pieces.

### 7. Stay until done

- Do not abandon a task partway because it got complex.
- Carry context across turns using session memory.
- If interrupted, resume from where the work stopped — don't restart from the
  top unless the interruption changed the goal.
- Sign off cleanly when the task is complete; don't linger with extra work.

## Pitfalls

- **Rushing to tool calls.** The most common failure. Understanding and reasoning
  before acting is not overhead — it prevents wrong actions.
- **Surface-level interpretation.** Read what the user actually wrote, not what
  you expect them to have written. If a request is ambiguous, ask.
- **Assuming state.** Check the actual system state (files, config, processes,
  running services) before designing a solution. Assumptions about state are the
  second most common failure.
- **Ignoring memory.** User preferences, corrections, and environment facts stored
  in memory are authoritative and active. Read them before starting.
- **Premature completion.** "Seems done" is not "is done." Verify.
- **Abandoning on complexity.** Complex tasks need more reasoning, not less.
  Stay with the task.

## When This Skill Activates

This skill governs HOW you approach tasks, so it is always in play during task
execution. It is especially important when:
- The task is new or unfamiliar
- The task involves a system you haven't fully audited yet
- The user's request is ambiguous or could be interpreted multiple ways
- The stakes are high (operational system, security, data loss risk)
- You feel pressure to "just do something" — that pressure is a signal to
  reason more, not less

## Relationship to Other Skills

- `software-development/systematic-debugging` — similar "understand first"
  philosophy but scoped to bug root-cause analysis, not general task approach.
- `software-development/plan` and `software-development/writing-plans` — planning
  workflow skills; this skill governs the reasoning that precedes planning.
- `autonomous-ai-agents/hermes-agent` — Hermes Agent configuration and operation;
  this skill governs the agent's internal reasoning approach, not the tool it
  runs on.

## References

- `references/cron-config-drift.md` — Hermes cron job config drift failure pattern
  and fix (diagnosed during a runtime audit session).
