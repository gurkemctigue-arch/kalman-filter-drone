# Existing Humble54 identity reports: per UUID

Descriptive extraction only; no per UUID acceptance threshold.

| Case | UUID | Correct | Wrong | Unknown | Full grid | Known coverage | Diagnostic frames |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| person_stage2_crossing_seed004 | ba2d6ef2-eeb8-451d-a703-8c7f4075e7ad | 219 | 0 | 103 | 322 | 0.680124 | 321 |
| person_stage2_crossing_seed004 | f5737fb4-e629-4098-9f2b-6eb848e683f0 | 430 | 0 | 1 | 431 | 0.997680 | 431 |
| person_stage3_multi_active_seed004 | f5a7aff1-b30f-4e20-993f-16b94e879ed7 | 217 | 0 | 105 | 322 | 0.673913 | 321 |
| person_stage3_multi_active_seed004 | e4bc9b68-40a4-43f5-a5e4-3995aad10246 | 431 | 0 | 1 | 432 | 0.997685 | 432 |
| car_stage2_crossing_seed004 | d29c84cf-fff4-47d7-a1a2-53caf4fbe837 | 211 | 0 | 111 | 322 | 0.655280 | 312 |
| car_stage2_crossing_seed004 | 7300755a-38c5-4c71-b621-4ea48062c823 | 429 | 0 | 3 | 432 | 0.993056 | 431 |
| car_stage3_multi_active_seed004 | 80993fb1-3d0a-4a8d-8fa4-aceccd6b6802 | 200 | 0 | 122 | 322 | 0.621118 | 297 |
| car_stage3_multi_active_seed004 | 367537b1-4604-4612-8c71-80945f51dd3a | 414 | 0 | 17 | 431 | 0.960557 | 417 |

Full unknown-cell reasons and contiguous runs are in summary.json. Diagnostic unknown-frame reasons are separate and do not explain every full-grid cell.

Four reports were opened once each, in sequence. Each buffer matched its original terminal SHA; buffer SHA was rechecked after parsing and file metadata stayed unchanged. No second file-content hash was performed.
