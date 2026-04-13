# Plan: Handle Missing Text in Kalimat API Search Results

## Metadata
- **ID**: plan-2026-04-12-search-results-missing-text
- **Status**: draft
- **Specification**: codev/specs/0020-search-results-in-tools-search.md
- **Created**: 2026-04-12

## Executive Summary
Filter out results without text content from the Kalimat API response in `SearchQuran.run()` and `SearchHadith.run()`, and make `pp_hadith` use safe `.get()` access. This is a single-phase fix — small scope, low risk.

## Success Metrics
- [ ] All specification criteria met
- [ ] New unit tests pass
- [ ] All existing tests pass
- [ ] `ruff check` and `ruff format` pass

## Phases (Machine Readable)

```json
{
  "phases": [
    {"id": "phase_1", "title": "Filter and defensive access"}
  ]
}
```

## Phase Breakdown

### Phase 1: Filter and defensive access
**Dependencies**: None
**Status**: pending

#### Objectives
- Filter out results lacking text content in `SearchQuran.run()` and `SearchHadith.run()`
- Make `SearchHadith.pp_hadith()` use safe `.get()` with string defaults
- Add unit tests for the filtering and safe-access logic

#### Deliverables
- [ ] `search_quran.py`: Add `_filter_results()` helper and call it in `run()`
- [ ] `search_hadith.py`: Add `_filter_results()` helper and call it in `run()`; convert `pp_hadith` to safe `.get()` access
- [ ] `tests/unit/test_search_quran.py`: Tests for filtering and formatting with navigational results
- [ ] `tests/unit/test_search_hadith.py`: Tests for filtering and safe access in `pp_hadith`

#### Implementation Details

**Filter helper for `SearchQuran`**:
Add a `_filter_results()` method that removes results where both `text` and `en_text` are absent or empty/whitespace. Log filtered result count and IDs at debug level.

**Filter helper for `SearchHadith`**:
Same pattern but checks `ar_text` and `en_text` (hadith uses `ar_text`, not `text`).

**`pp_hadith` safe access**:
Replace all direct key access (`h["en_text"]`, `h["grade_en"]`, `h["source_book"]`, etc.) with `.get("key", "")`.

#### Acceptance Criteria
- [ ] Query "Ayat Ul Kursi" no longer produces empty/placeholder entries
- [ ] `pp_hadith` does not raise `KeyError` on incomplete results
- [ ] All new tests pass
- [ ] All existing tests pass
- [ ] `ruff check` and `ruff format` clean

#### Test Plan
- **Unit Tests**: 
  - `test_filter_removes_navigational_results` — mixed results, verify navigational ones removed
  - `test_filter_preserves_all_normal_results` — all results have text, none filtered
  - `test_filter_all_navigational` — all navigational, returns empty list
  - `test_filter_empty_string_text` — results with empty/whitespace text fields are filtered
  - `test_pp_hadith_missing_fields` — verify safe access with missing keys
  - `test_pp_ayah_navigational` — verify pp_ayah handles a result with just id
  - `test_format_as_ref_list_with_filtered_results` — verify ref list excludes filtered results
  - `test_format_as_tool_result_with_filtered_results` — verify tool result excludes filtered results

#### Rollback Strategy
Revert the single commit.

#### Risks
- **Risk**: Filter predicate too aggressive, removing valid results
  - **Mitigation**: Only filter when ALL text fields are missing; unit tests verify preservation of valid results
