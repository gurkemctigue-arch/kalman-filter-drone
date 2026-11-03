# Historical NTFS text compression: fixed sample preparation 02

Status: **PREPARED ONLY; NO COMPRESSION OR VHD OPERATION EXECUTED**.

This is a bounded follow-on to the metadata-only survey, not a capacity
approval. It does not change the fixed storage assumptions, source snapshots,
experiment evidence or formal denominator. The preparing agent read only named
small source/metadata files and queried Windows free-space/file attributes.
It did not call WSL, hash/read a result payload, traverse another tree, open a
bag/model/VHD, compress, delete, trim, stop a distribution or compact a VHD.

## Observed capacity and the unresolved budget

The original survey file is
`tools/diagnostics/text_storage_metadata_survey01/survey01.json`, raw SHA256
`778eb6116ee55140f2ea7f48c64b4ec46d872b3051c439b6b8a52d9710817db9`.
Its 1,105 historical uncompressed text candidates occupied 19,646,279,680
allocated bytes (18.297 GiB). Telemetry alone occupied 16,926,420,992 allocated
bytes (15.764 GiB). This is the pool's current allocation, **not** recoverable
space or an observed compression ratio. It excludes recent/active outputs,
reparse points, multiple hard links, encrypted and sparse files.

A later Windows `Get-PSDrive` observation in this preparation found D free
109,909,622,784 bytes (102.361 GiB), C free 16,007,856,128 bytes and E free
10,363,125,760 bytes. These are point-in-time observations during an active
experiment, not the independent inventory required for the final budget.

The existing assumptions reserve 22 GiB for remaining build/delivery, in
addition to per-slot growth and the independent temporary reserve. On that D
observation, even ignoring temporary space and all remaining development
growth, the mean measured formal-cell footprint would have to be no more than
approximately 242 MiB to fit all 280 slots after the existing 1.15 growth factor
and 16 MiB per-slot allowance. This arithmetic is only an early risk signal.
One observed compressed fault bag exceeding 1 GB cannot establish the mean of
all 28 development conditions; only the complete measurement can settle it.

The candidate pool cannot recover more than its entire 18.297 GiB allocation,
and real savings will be smaller. Do not claim that text compression alone can
make the formal280 budget fit. Do not book estimated savings into the budget.

## Fixed two-file sample

These paths are relative to the existing project `results/`. They were selected
from the original survey's retained metadata before any compression test. The
selection covers a large telemetry file and an approximately 80 MiB telemetry
file; it is not selected by engineering PASS/FAIL or expected compression.

| Exact relative path | Original logical bytes | Original allocation bytes |
| --- | ---: | ---: |
| `frozen_fullplan_v4_humble35/reliability_v4_humble35_surface01_car_stage2_crossing_seed004/telemetry.jsonl` | 195,924,034 | 195,928,064 |
| `frozen_fullplan_v4_humble43/reliability_v4_humble43_probe01_car_stage1_velocity_seed004/telemetry.jsonl` | 82,657,557 | 82,661,376 |

Total original logical bytes: 278,581,591 (265.676 MiB). Both are historical
files; neither belongs to active humble54, probe02, owner04/05 or final55. The
sample measures telemetry only. It does not establish a compression ratio for
logs, JSON reports, images, videos, bags, or the entire candidate population.

## Serial execution gate and measurement

Root can execute this reversible Windows operation after the current original
experiment command, its native collector and held Windows owner handles have
closed, then the existing native-idle check passes. Do not compete with flight,
cold-build, bag analysis, export or another compression operation. Save a new
external receipt; do not overwrite the original survey or experiment files.

1. Bind the actual sample paths to the project results root and reject any
   reparse component, escape, alternate stream or changed sample. Recheck the
   original logical size/mtime, single hard link, age >=24 hours, uncompressed,
   non-sparse and non-encrypted attributes. Require NTFS compression support.
2. For each exact file, open a read handle that denies writers while preserving
   ordinary read sharing. Capture creation identity/file ID, logical size,
   mtime, attributes, hard-link count and actual allocation. Reuse the survey's
   `GetFileInformationByHandleEx(FileStandardInfo)` allocation method; an
   uncompressed `GetCompressedFileSizeW` can equal logical bytes and should not
   replace it. Stream a complete pre-operation SHA256 and record elapsed time.
   Close this pre-read handle before `compact.exe` obtains its own handle; do
   not hold a deny-write handle across the compression command. If pre-read
   stability cannot be established, stop rather than skip to a different file.
3. Run Windows `compact.exe /C /F /Q` on **one exact named file at a time**.
   No `/S`, wildcard, directory argument, `/EXE`, global policy or recursive
   action. Preserve actual argv, stdout/stderr, start/end UTC, monotonic
   duration and return code. A command returning zero is not sufficient proof
   of saving; verify the file's compressed attribute and allocation afterwards.
4. Reopen a stable read handle denying writers and stream the complete file
   again through normal Windows reads. Require equal
   pre/post SHA256 and logical size. This full read verifies transparent
   decompression. Recheck file identity, mtime, hard-link count and attributes;
   record changes rather than silently restoring metadata. Record actual
   before/after allocation, saving and read timings per file. Stop on an error
   or byte/identity mismatch and retain the partial receipt.
5. Observe D free space before/after, but attribute the measured saving to the
   sample's allocation delta: other processes can change global free space.
   Do not extrapolate this sample as a measured total saving. Any larger batch
   needs a fixed manifest of revalidated historical files and the same raw-hash
   and per-file allocation checks. Preserve every failed/interrupted sample.

The repository currently has the metadata survey API but no reviewed NTFS
compression executor. This document deliberately does not introduce an
automatic executor. A future command should invoke the existing Windows
`compact.exe` directly, not build destructive shell text or move files to a
new archive. The original paths and raw bytes remain readable by current
experiment tools; no source/evidence JSON needs rewriting.

## VHD and final-budget boundary

`tools/reliability_v4_guard.py` already supplies `NativeStorage.vhd_path`,
`volume`, `logical_free` and the `storage-probe` CLI. The existing followon05
execution card records the required physical-inventory command. It resolves
the current distribution's registry-backed VHD path and actual Windows volume
identities, preventing an ext4 virtual free count from being mistaken for D
capacity. The storage budget tool consumes that inventory together with all
28 actual cells and the unchanged assumptions.

There is no reviewed VHD trim/compact executor in this repository. A VHD file's
logical length alone does not reveal its host allocated bytes, allocated guest
blocks or reclaimable discarded blocks. Do not NTFS-compress an active WSL
VHD, apply sparse mode, run `fstrim`, stop WSL or compact a VHD during a native
task. A later separate idle-window investigation must first measure host
allocation and guest used/free space, identify the exact distribution and
other WSL users, and determine whether reclaimable blocks exist. Compaction
cannot reclaim live source/evidence blocks. No saving is presently measured.

After any actual optimization, collect a fresh physical inventory and run the
existing unchanged full28 budget. Retain a negative budget result and resolve
the real shortfall; do not lower growth factors, reserves, repeat counts,
recording duration or evidence coverage to manufacture a fit.
