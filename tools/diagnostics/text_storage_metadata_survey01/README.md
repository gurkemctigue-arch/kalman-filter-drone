# Historical text metadata survey 01

`survey01.json` is the original Windows metadata-only result from 2026-11-03
05:00:51--05:01:21 UTC. No file was compressed, deleted or rewritten; no WSL
command, VHD, bag, model, image or video payload was opened.

The bounded traversal completed within its declared exclusions in 30.047 s:
3,300 directories, 57,675 entries, 36,944 selected text files and zero errors.
Recent files, reparse points, active monitor/progress directories and names
containing `probe02`, `owner04`, `followon05` or `final55` were excluded.

The volume reports NTFS compression support and was not globally compressed.
The final free-space observation was 111,263,571,968 bytes. Selected text files
totaled 25,969,480,888 logical bytes and 25,708,482,968 allocated bytes. There
were 1,105 historical uncompressed candidates of at least 1 MiB and 24 hours
age, totaling 19,644,008,160 logical bytes and 19,646,279,680 allocated bytes
(18.297 GiB). These candidates excluded sparse/encrypted files and multiple
hard links. The receipt provides grouping by version, extension and basename.

The script uses `GetVolumeInformationW`, `GetDiskFreeSpaceExW`,
`GetCompressedFileSizeW` and `GetFileInformationByHandleEx(FileStandardInfo)`.
File handles request only `FILE_READ_ATTRIBUTES`, allow READ/WRITE/DELETE
sharing and are closed after the metadata query. AllocationSize is the
allocation basis; the separate GetCompressedFileSizeW result can equal the
logical size for an uncompressed file. Shared filesystem metadata is excluded.

This measures a candidate pool, not a compression ratio or reclaimable space.
No sufficiency conclusion for formal280 follows. Any future compression
measurement needs a fixed historical sample, before/after allocation and raw
content hash checks, observed runtime and decompression/read verification. Such
a measurement was not run here.

Original raw SHA-256:

- `survey.py`: `a4a88958d2f5075dc2cc13db01e35ea2a595f7513a3f8be39c1247da47f91a6b`
- `survey01.json`: `778eb6116ee55140f2ea7f48c64b4ec46d872b3051c439b6b8a52d9710817db9`

Local `.gitattributes` protects these exact bytes from line-ending conversion.
