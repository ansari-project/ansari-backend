# Specification: Handle Missing Text in Kalimat API Search Results

## Metadata
- **ID**: spec-2026-04-12-search-results-missing-text
- **Status**: draft
- **Created**: 2026-04-12
- **Issue**: #20

## Clarifying Questions Asked
The issue report provided thorough detail including the exact API payload and response. Key observations from the issue:

1. Q: When does this occur? A: When the Kalimat API returns a "navigational" result (e.g., `{'id': '2:255', 'navigational': 1, 'type': 'quran_verse'}`) — the first result has no `text` or `en_text` keys.
2. Q: Is the navigational result useful? A: Yes — it correctly identifies the ayah (2:255 is Ayat ul-Kursi), but the API flags it as a navigational match rather than a semantic match, so it omits the text fields.
3. Q: Does `search_hadith.py` have the same issue? A: `pp_hadith` uses direct key access (`h["en_text"]`, `h["grade_en"]`, etc.) which would raise `KeyError` if the API ever returned a similar navigational result for hadith. The same defensive pattern should be applied.

## Problem Statement
The Kalimat search API (`api.kalimat.dev/search`) can return results where certain fields (`text`, `en_text`) are absent. Specifically, "navigational" results (where `navigational: 1`) contain only `id` and `type`. When `search_quran.py` processes these results, it outputs misleading placeholder text ("Not retrieved") instead of clearly indicating the result is a navigational match. More critically, `search_hadith.py` uses direct dict key access (`h["en_text"]`, `h["grade_en"]`) which would raise a `KeyError` on any result missing those keys.

## Current State
- `search_quran.py:pp_ayah` uses `.get("text", "Not retrieved")` — safe from crashing but produces misleading output.
- `search_quran.py:format_as_ref_list` and `format_as_tool_result` use `.get()` — safe from crashing but include empty/meaningless entries for navigational results.
- `search_hadith.py:pp_hadith` uses direct key access (`h["en_text"]`, `h["grade_en"]`, `h["source_book"]`, etc.) — will crash with `KeyError` on incomplete results.
- No filtering of navigational results is done; they are passed through to the LLM as content-bearing results.

## Desired State
- Results lacking text content are filtered out before formatting. The filter predicate is: a result is removed if it has **no non-empty text field** — specifically, for Quran results, both `text` and `en_text` must be absent or empty; for Hadith results, both `ar_text` and `en_text` must be absent or empty. Empty strings and whitespace-only strings count as "missing." This is independent of the `navigational` flag — any result without text content is filtered regardless of the reason.
- When all results are filtered out, the tool returns an empty list, consistent with existing empty-result behavior (the caller already handles this case with "No results found").
- `search_hadith.py:pp_hadith` uses safe `.get()` access with string defaults (e.g., `""`) for all fields, consistent with the defensive pattern already partially used in `search_quran.py`.
- Logging records when results are filtered: the log message includes the count of filtered results and their IDs/types for debugging.

## Stakeholders
- **Primary Users**: End users querying Quran/Hadith through Ansari
- **Technical Team**: Ansari backend maintainers

## Success Criteria
- [ ] Navigational results (missing `text` and `en_text`) are filtered out before formatting
- [ ] `search_hadith.py:pp_hadith` uses safe `.get()` access for all fields
- [ ] The specific query from issue #20 ("Ayat Ul Kursi") no longer produces empty/placeholder entries
- [ ] All existing tests pass
- [ ] New unit tests cover the navigational result edge case

## Constraints
### Technical Constraints
- Must not alter the Kalimat API contract — the fix is purely client-side filtering
- Must maintain backward compatibility: no changes to method signatures or return types
- Must handle both Quran and Hadith search tools consistently

## Assumptions
- The Kalimat API will continue to use the `navigational` field to indicate results without text
- Results without both `text` and `en_text` carry no useful content for the LLM
- The API response format is otherwise stable

## Solution Approaches

### Approach 1: Filter navigational results in `run()` (Recommended)
**Description**: Add a filtering step in `SearchQuran.run()` and `SearchHadith.run()` that removes results lacking text content before they reach any formatting method.

**Pros**:
- Single point of filtering — all downstream methods automatically benefit
- Clean separation: `run()` returns only content-bearing results
- Logging at the filter point gives clear debugging info

**Cons**:
- Slightly changes the semantics of `run()` (filters raw API output)

**Estimated Complexity**: Low
**Risk Level**: Low

### Approach 2: Handle in each formatting method individually
**Description**: Add skip/filter logic in `pp_ayah`, `format_as_ref_list`, `format_as_tool_result`, etc.

**Pros**:
- `run()` returns the raw API response unchanged

**Cons**:
- Duplicated filtering logic across multiple methods
- Easy to miss a method, leaving the bug partially unfixed
- More code to maintain

**Estimated Complexity**: Low
**Risk Level**: Medium (due to duplication)

## Open Questions

### Critical (Blocks Progress)
- [x] None — the issue and fix are well-understood

### Important (Affects Design)
- [x] Should we filter in `run()` or in formatting methods? Decision: Filter in `run()` (Approach 1)

## Performance Requirements
- No performance impact — filtering a list of ~10 results is negligible

## Security Considerations
- None — this is a read-only formatting fix

## Test Scenarios
### Functional Tests
1. API returns all normal results (no navigational) — all results preserved
2. API returns a mix of normal and navigational results — navigational ones filtered out
3. API returns only navigational results — empty result set
4. `pp_hadith` handles results with missing fields gracefully

### Non-Functional Tests
- None required for this scope

## Dependencies
- **External Services**: Kalimat API (`api.kalimat.dev/search`)
- **Libraries/Frameworks**: None new

## Risks and Mitigation
| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|-------------------|
| Kalimat API changes navigational result format | Low | Low | Filtering checks for absence of both text fields, not for `navigational` flag specifically |
| Hadith API returns similar incomplete results | Low | Medium | Apply same defensive pattern to `search_hadith.py` |

## Expert Consultation
**Date**: 2026-04-12
**Models Consulted**: Gemini Pro and GPT-5 Codex

### Gemini Pro Feedback
- **APPROVE** (HIGH confidence)
- Key issue: Hadith API uses `ar_text` (not `text`) for Arabic text — filter predicate must check the correct field per tool
- Key issue: `.get()` calls in `pp_hadith` need string defaults to avoid `TypeError` during string formatting

### GPT-5 Codex Feedback
- **COMMENT** (HIGH confidence)
- Clarify the exact filter predicate: filter on absence of text content, not on `navigational` flag
- Define whether empty/whitespace-only strings count as "missing" (decision: yes, they do)
- Clarify empty-result behavior (decision: return empty list, consistent with existing handling)
- Logging should include count and IDs of filtered results

All feedback has been incorporated into the Desired State and Solution Approaches sections above.
