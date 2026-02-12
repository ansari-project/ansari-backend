# INVESTIGATE Phase Prompt

You are executing the **INVESTIGATE** phase of the BUGFIX protocol.

## Your Goal

Understand the bug, reproduce it, identify the root cause, and assess whether it's fixable within BUGFIX scope (< 300 LOC).

## Context

- **Issue**: #{{issue.number}} — {{issue.title}}
- **Current State**: {{current_state}}

## Process

### 1. Read the Issue

Read the full issue description. Identify:
- What is the expected behavior?
- What is the actual behavior?
- Are there reproduction steps?
- Are there error messages or screenshots?

### 2. Reproduce the Bug

Before fixing anything, confirm the bug exists:
- Follow the reproduction steps from the issue
- If no steps are given, infer them from the description
- Document the exact reproduction steps you used
- If you **cannot** reproduce, signal `BLOCKED` with details

### 3. Identify Root Cause

Trace the bug to its source:
- Read the relevant code paths
- Use grep/search to find related code
- Identify the exact file(s) and line(s) causing the issue
- Understand **why** the bug occurs, not just **where**

### 4. Assess Complexity

Determine if this is BUGFIX-appropriate:
- **< 300 LOC change**: Proceed with BUGFIX
- **> 300 LOC or architectural**: Signal `TOO_COMPLEX` to escalate

Consider:
- How many files need to change?
- Does it require new abstractions or refactoring?
- Are there cascading effects?

## Output

By the end of this phase, you should know:
1. The exact root cause
2. Which files need to change
3. The approximate size of the fix
4. Whether it's BUGFIX-appropriate

## Signals

When investigation is complete:

```
<signal>PHASE_COMPLETE</signal>
```

If the bug is too complex for BUGFIX:

```
<signal>TOO_COMPLEX</signal>
```

If you're blocked (can't reproduce, missing context, etc.):

```
<signal>BLOCKED:reason goes here</signal>
```
