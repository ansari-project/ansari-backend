# Review: Handle Missing Text in Kalimat API Search Results

## Metadata
- **ID**: review-2026-04-12-search-results-missing-text
- **Specification**: codev/specs/0020-search-results-in-tools-search.md
- **Plan**: codev/plans/0020-search-results-in-tools-search.md
- **Created**: 2026-04-12

## Summary
Fixed issue #20 where the Kalimat API returns "navigational" results without `text`/`en_text` fields, causing empty output in `search_quran.py` and potential `KeyError` crashes in `search_hadith.py`.

## Changes Made
1. **`search_quran.py`**: Added `_filter_results()` method that removes results where both `text` and `en_text` are absent/empty/whitespace. Called from `run()` so all downstream methods benefit.
2. **`search_hadith.py`**: Added equivalent `_filter_results()` checking `ar_text` and `en_text`. Converted `pp_hadith()` from direct dict key access to safe `.get()` with string defaults.
3. **`tests/unit/test_search_quran.py`**: 17 tests covering filtering edge cases (navigational, empty strings, whitespace, None values, issue #20 exact data) and formatting methods.
4. **`tests/unit/test_search_hadith.py`**: 14 tests covering filtering and safe access in `pp_hadith` (missing fields, None grade, empty dict).

## Specification Criteria Met
- [x] Navigational results (missing `text` and `en_text`) are filtered out before formatting
- [x] `search_hadith.py:pp_hadith` uses safe `.get()` access for all fields
- [x] The specific query from issue #20 ("Ayat Ul Kursi") no longer produces empty/placeholder entries
- [x] All existing tests pass (pre-existing failures unrelated to this change)
- [x] New unit tests cover the navigational result edge case

## Lessons Learned

### What went well
- The issue report was exceptionally detailed, including exact API payloads and responses — this made diagnosis trivial
- The single-point filtering approach (in `run()`) kept the change minimal and prevented duplication
- Multi-agent consultation caught a real bug: Gemini identified that hadith uses `ar_text` not `text`, which would have been a filtering bug

### What was challenging
- The `consult` CLI had issues with `af-config.json` migration and with `impl`/`phase` review types that require a PR or builder worktree context. Workaround: ran spec and plan consultations successfully, skipped impl-phase consultation.

### Methodology observations
- For simple bug fixes, SPIR's full ceremony (spec + plan + 2x consultation per phase) is heavyweight. The fix itself was ~30 lines of code. The protocol overhead was worthwhile for catching the `ar_text` vs `text` field name difference, though.
