# CLEAN Phase Prompt

You are executing the **CLEAN** phase of the MAINTAIN protocol.

## Your Goal

Remove the dead code and unused dependencies identified in the audit phase.

## Context

- **Current State**: {{current_state}}

## Prerequisites

Read the audit report from the previous phase:
```bash
ls -la codev/maintain/
cat codev/maintain/*.md | tail -100
```

## Process

### 1. Remove Dead Code

For each item identified in the audit:

1. Verify it's truly unused (double-check with grep)
2. Use `git rm` for tracked files
3. For untracked files, move to `.trash/` before deleting

**CRITICAL**: Use soft deletion first:
```bash
mkdir -p codev/maintain/.trash/$(date +%Y-%m-%d)
mv path/to/file codev/maintain/.trash/$(date +%Y-%m-%d)/
```

### 2. Remove Unused Dependencies

```bash
# Remove from package.json
npm uninstall <package-name>
```

### 3. Verify Build After Each Removal

After each significant removal:
```bash
npm run build
npm test -- --exclude='**/e2e/**'
```

If build fails, revert the change and investigate.

### 4. Commit Changes

Make atomic commits for each logical change:
```bash
git add <specific-files>
git commit -m "[Maintain] Remove unused X"
```

**NEVER use `git add -A` or `git add .`**

## Important Rules

1. **One removal at a time** - Don't batch unrelated changes
2. **Verify after each removal** - Build must pass
3. **Document what was removed** - Update the maintenance run file
4. **Soft delete first** - Move to .trash/ before permanent deletion
5. **Check for side effects** - Grep for references before removing

## Output

Update the maintenance run file with:
- What was removed
- Build/test status after removal
- Any issues encountered

## Signals

When all dead code is removed and build passes:

```
<signal>PHASE_COMPLETE</signal>
```

If blocked:

```
<signal>BLOCKED:reason</signal>
```
