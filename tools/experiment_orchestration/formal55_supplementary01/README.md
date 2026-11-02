# Formal55 supplementary guard-path repair

This is a new external source version. The original `formal54_supplementary01`
directory is unchanged. `original54_copy_manifest01.json` records all 21 files
copied before adaptation; `original54_source` preserves the five original
source/test files and their original canonical
`b0c4f60b438455569f46f2160ac4bb0e46202fca311a57f9b25181fe7d4b680c`.
Copied historical receipts, `new_preflight_describe01.json`, and `HANDOFF.md`
remain formal54 evidence and documentation. They are not current formal55
validation results. Use the new `formal55_*` artifacts for this version.

Current source canonical SHA256:
`b8f75eccb143871130671a00ad5cf75fe0768e43bc46bb0a99c2586f207b0580`.
The actual Windows inert `formal55_describe01.json` and adjacent receipt record
this value. It identifies source bytes and policy, and grants no execution.

## Narrow behavior change

The old metadata preflight rejected a sealed admission whose guard lived
outside the final algorithm root. The new `guard_source_binding` first applies
the unchanged `checked()` gate to the actual ordinary source file, canonical
absolute path and SHA. It then accepts exactly either:

- the existing `final_root/tools/reliability_v4_guard.py` binding;
- `/root/uav_tracking_snapshot_audit54_tools01/tools/reliability_v4_guard.py`
  with SHA256
  `e64e9da6a5180d70b32c6b2b3076abe4bbc52d4b748395bf7f8af61e6a7e3a8e`.

An identical copy at another external path is rejected. A changed or rehashed
file at the fixed path is rejected. The guard remains among the original input
pins and is checked again immediately before exec.

The preflight does not import or execute a guard. The unchanged formal48 adapter
still loads the actual sealed `manifest.tool` bytes, verifies their SHA, checks
the loaded module's physical `__file__`, and leaves admission decisions to the
guard. Its source, command prefix, resolutions, signal ownership and execution
behavior are unchanged.

## Fresh prospective identity

The contract fields and metadata semantics are unchanged. This new source uses
`FORMAL55_SUPPLEMENTARY_BINDING_ONLY_NOT_ADMISSION` and
`FORMAL55_SUPPLEMENTARY_PREFLIGHT_CHECK_ONLY_NOT_GUARD_ADMISSION` identities.
The explicit actual-adapter identity remains
`FORMAL54_EXPLICIT_REVIEWED_ADAPTER_BINDING_NOT_ADMISSION`, because the actual
formal48 adapter and its reviewed identity did not change.

`tool_manifest` includes the fixed guard policy and all six current source/test
files. A future caller must use its newly reviewed canonical digest and the new
directory, contract kind and audit kind. An old54 contract or canonical cannot
stand in for this new prospective binding. No actual supplementary contract,
selection, detection protocol, formal plan, admission or flight was created by
this repair.

The current shell keeps the original sibling-script pattern. Serial54 and
durable54 accept an explicitly pinned new command prefix without source
changes. The future card must bind this new directory and canonical; it must
also retain the same fixed external guard path through the real safety and
formal manifest chain.

## Validation scope

The existing three test files are copied byte for byte and exercise the same
55 synthetic metadata/fake-exec cases in the new sibling directory. They still
read the approved producer fixtures from the common external parent. Rerunning
historical independent fixtures is regression evidence, not a new independent
review.

`test_formal55_guard_binding.py` adds eight cases for the production fixed
literal, legacy compatibility, fixed-path acceptance, fake delegation, wrong
path or SHA, changed bytes, and mutation immediately before fake exec. Windows
physical-file cases relocate the constant only inside synthetic fixture
namespaces and use tiny inert source bytes. The production Linux literal is
checked separately with an explicit mock file-check boundary. These cases do
not prove that the actual native fixed guard was imported or executed.

Fresh `formal55_windows_tests01.log` and `formal55_windows_tests01.json` retain
the current invocation, terminal outcome, and source pins before and after.
The run completed 63 tests with 63 passes in 230.991 seconds; all six current
source/test pins were unchanged before and after the run.
No WSL, native adapter/guard, simulation, model or bag was read or run.
