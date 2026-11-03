# Interrupted batch recovery and complete new plan

`originals/` is a byte-exact snapshot of 42 named small records (1,087,460 bytes)
with original source paths, hashes and sizes in `manifest.json`. `snapshot.py`
recreates it only in a new directory; it does not start native work.

The old collector03 stopped on a real DrvFS atomic-replacement permission
error. Its independently grouped flight subsequently ended, but the parent
flight-command exit code was not observed. The original public runner therefore
recorded slot8 as INTERRUPTED, never inferred COMPLETED from its saved flight
summary. Earlier seven original terminals remained unchanged.

The old probe01 has eight attempted terminals: 3 PASS, 2 INCOMPLETE_EVIDENCE,
2 FAIL and 1 INTERRUPTED; eight slots are unattempted. Old owner/waiter states
remain stopped. They cannot qualify a complete28 capacity result.

The original public CLI registered complete extension16 probe02 with identical
frozen source/model/protocol bindings and development seed4. No formal seeds
1000–1009 were used. Registration alone launched no flight; actual new execution
is recorded separately by owner04. Original core12 and independent safety03
are reusable only after their exact source and evidence bindings are checked.

The archived actual sharing probe is deliberately tiny: old03 failed on a
real errno13 and retained original destination bytes; new04 encountered the
same OS conflict, retried and wrote successfully after release. Both real
helper commands exited zero, and new04 left no temporary file. This is a
file-sharing result, not a collector-loop, ROS, bag, flight or capacity result.
