# Ansari Analysis Directory

This directory contains all analysis scripts, reports, and data from the comprehensive MongoDB thread analysis project.

## Directory Structure

```
analysis/
├── scripts/           # Python analysis scripts
├── reports/           # Generated reports and findings
├── data-local/        # Local data files (gitignored)
└── README.md         # This file
```

## 📁 Scripts (`/scripts`)

Contains all Python scripts used for analysis:

### Core Analysis Scripts
- `analyze_threads_v2.py` - Main v2 analysis with consolidated categories
- `analyze_threads_v2_parallel.py` - Parallel processing version (30 workers)
- `comprehensive_analysis_summary.py` - Generate comprehensive statistics

### Quran-Specific Analysis
- `analyze_quran_clusters.py` - Cluster analysis of Quran questions (100 samples)
- `analyze_quran_500.py` - Extended cluster analysis (500 samples)
- `analyze_quran_clusters_multisize.py` - Multi-sample size comparison
- `extract_quran_no_pii.py` - Extract Quran questions with no PII
- `reclassify_quran_top7.py` - Reclassify into top 7 categories

### PII Analysis
- `extract_pii_examples.py` - Extract examples of different PII levels
- `extract_category_examples.py` - Extract examples by category
- `pii_histogram_text.py` - Generate PII confidence histogram

### Utilities
- `monitor_v2_progress.py` - Monitor parallel analysis progress
- `monitor_loop.py` - Continuous monitoring script
- `check_missing_threads.py` - Verify thread coverage
- `reclassify_categories.py` - Post-processing category consolidation

## 📊 Reports (`/reports`)

Generated analysis reports:

### Final Reports
- `ANSARI_V2_ANALYSIS_FINAL_REPORT.md` - **Main v2 analysis report** with:
  - Consolidated categories (Fiqh includes halal/haram)
  - PII confidence scores (0.0-1.0)
  - 22,081 threads analyzed
  - 99.99% success rate

- `ANSARI_FINAL_REPORT_CONSOLIDATED.md` - Consolidated category analysis
- `ANSARI_THREAD_ANALYSIS_FINAL_REPORT.md` - Initial comprehensive report

### Summary Reports
- `analysis_completion_summary.md` - Analysis completion statistics
- `analysis_final_corrected_summary.md` - Corrected thread counts

## 💾 Data Local (`/data-local`) - GITIGNORED

Contains analysis data and results:

### Directories
- `analyzed_data/` - Original v1 analysis results
- `analyzed_data_v2/` - V2 analysis with improved categories
- `feedback_data/` - User feedback analysis

### Key Data Files
- `quran_questions_no_pii.txt` - 1,861 Quran questions with no PII
- `comprehensive_analysis_final_summary.json` - Complete statistics
- `quran_cluster_analysis.json` - Quran clustering results
- `quran_500_analysis.json` - Extended clustering analysis
- Various batch processing logs and results

## Key Findings

### Topic Distribution (V2 Analysis)
- **Fiqh**: 40.4% (includes all halal/haram questions)
- **Islamic Life & Thought**: 23.9%
- **Quran**: 8.5%
- **Other**: 8.0%
- **Hadith**: 6.5%

### PII Analysis
- **97.7%** of threads have low PII risk (confidence < 0.3)
- **93.4%** have zero PII (confidence = 0.0)
- Only **1.0%** high risk (confidence ≥ 0.7)

### Language Distribution
- **English**: 74.3%
- **Arabic**: 10.2%
- **Urdu**: 5.0%
- **Indonesian**: 2.1%

## Usage

### Running V2 Analysis
```bash
python analysis/scripts/analyze_threads_v2_parallel.py --workers 30
```

### Monitoring Progress
```bash
python analysis/scripts/monitor_v2_progress.py
```

### Extracting Non-PII Quran Questions
```bash
python analysis/scripts/extract_quran_no_pii.py
```

## Notes

- All data in `/data-local` is gitignored to prevent large files from being committed
- The v2 analysis uses Gemini 2.5 Flash for classification
- Analysis achieved 99.99% success rate (only 2 errors out of 22,081 threads)