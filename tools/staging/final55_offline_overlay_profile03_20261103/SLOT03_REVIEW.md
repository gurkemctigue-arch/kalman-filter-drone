# Slot03 historical unknown qualification

The original profile02 slot source (`945717...`) remains unchanged. Copy03 adds
only `validate_slot(..., reviewed_unknown=None)`. The default retains the strict
original behavior. A supplied value must be exactly `root_review` (raw file
binding) plus `exception` (equal to that review's `historical_unknown`).

The named review must preserve the closed metadata stop, original plan, exact
slot terminal SHA, `INCOMPLETE_EVIDENCE`, the single explicit short-window null,
and the exact `HISTORICAL_UNKNOWN_RETAINED` row. It must postdate actual verified
outer closure. Its fresh input review must bind this same original terminal and
surface report, retain the incomplete verdict, report no errors/known algorithm
failures, and bind its extraction/visual metadata. Only the authenticated plan's
`frozen_root/results` alias maps to its `results_root`; there is no broad root
mapping. All shutter, long-loss safety and other unknown checks stay strict.

The actual review is `root_review.json` SHA
`eac4f501a771b6acc7ecf3c88a0765165506350815c20bea94ffd3b9ef26887d`.
The exact original dropout terminal is SHA
`c09f95ee3c4d5f14847bcbea82e8795b11cab6f5184fe735abac4c22decaeba8`.
Neither the original report's null nor its engineering verdict is rewritten.

`slot03_windows01_receipt.json` records 19/19 passing Windows small tests:
5 new original-metadata/tamper tests and 14 copied base tests. Source snapshots
match the before/after hashes. No WSL/native task, bag, model or image payload
was opened, and no production continuation was launched by these tests.
