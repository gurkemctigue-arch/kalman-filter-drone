# Complete new development collection, owner04

The unchanged frozen54 flight system is evaluated through its original public
runner and a new complete 16-slot extension plan, seed4. The old probe01 batch
retains eight attempted terminals (including one INTERRUPTED) and eight
unattempted slots. It is not combined with selected new successes.

The new collector source SHA256 is
`bf9168f2b5b6dc31e43c187d894f860a4d77e780ded6a4b453c2545c5b5aee0e`.
Its fixed plan SHA256 is
`1f7ff9559bcf9b1b02528a771f046481712a0ff5ec33eb961fe90310d1dcca54`;
entry03 SHA256 is
`d9cc1f1876a5ed9a358697b29644e7aa7a3c192e0bdd2a2a7d37c208e74f06a6`.

This revision repairs metadata supervision: unique atomic-write temporary files,
bounded real sharing-conflict retries, cleanup, actual child exit observation
before an exceptional owner exits, source/process creation identities, and
exact original START binding. It starts only unattempted original pending slots,
uses no historical evidence exceptions, and never retries a failed attempt.
Known performance failures are retained; infrastructure, source, unknown
evidence and safety faults stop the next launch.

All 23 lightweight supervision tests passed in actual UAVHumble22 Linux. These
use tiny owned fake commands and are not flight tests. The separate actual
Windows/DrvFS experiment reproduced an old03 real errno13 failure and observed
71 real errno13 exceptions within the new04 writer before success after handle
release. That proves the tested file-sharing repair, not flight acceptance.
Byte-exact test receipts and interruption/registration records are archived in
`../humble54_probe02_recovery01/originals/`.

The real collector output is intended to use Linux ext4, outside frozen source
and original results. An independent Windows monitor and external held-process
handles record actual command exits. New complete16 execution, capacity,
final55 freezing, formal admission and formal280 are separate later outcomes.
