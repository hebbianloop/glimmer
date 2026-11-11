# Real container qualification — 11 November 2026

One synthetic method passed a real execution and a fresh replay through the
installed Glimmer CLI, DataLad, git-annex and Docker. All 13 acceptance scenarios
passed at source commit `aeee354dc335f4a646e82645f8de2b7047df161b`.
The runner and schema are unchanged from the prerequisite
[core PR13](https://github.com/hebbianloop/glimmer/pull/13), commit
`44b6be49954fed29a7566abad1f637b8583e31e6`. This is example-level acceptance,
not acceptance of the hosted app or a scientific result.

Task: [web32](https://github.com/hebbianloop/glimmer-web/issues/32).
Parent: [completion plan web27](https://github.com/hebbianloop/glimmer-web/issues/27).
Master: [web2](https://github.com/hebbianloop/glimmer-web/issues/2).

## Evidence

[qualification.json](qualification.json) is the machine-readable result, including
source and evidence hashes, actual image identity, engine version, each case's
checks and the separate verdicts. [live-evidence.tar.gz](live-evidence.tar.gz)
contains each tested definition, Glimmer manifest, helper receipt, CLI log,
DataLad run message and output bytes. Its SHA-256 is
`c40780a4215b4c2db18014805bb810866aa780068b55274d2cebd6d1ba2a8cc6`.

| Scenario | Actual verdict | Additional acceptance evidence |
|---|---|---|
| Forward execution | `executed` | Real container, pinned archive, two exact products |
| Fresh replay | `checks-passed` | Raw-byte match; count, mean and sum agree at explicit zero tolerance |
| Changed input | `gate-failed` | Content pin fails while the format validator passes; no execution |
| Missing input | `inputs-unavailable` | Input absent; no execution |
| Invalid input | `gate-failed` | New Git pin matches invalid bytes; the format validator rejects them |
| Missing validator | `gate-failed` | Content pin passes; validator executable is unavailable |
| Changed image | `error` | Archive digest rejected before invocation |
| Missing image | `error` | Archive availability rejected before invocation |
| Failed method | `error` | Container command exits 23; no products |
| Missing output | `error` | Command completes; declared numeric output is absent |
| Wrong baseline | `mismatch` | Raw-byte and numeric comparisons both fail |
| Timeout | `error` | Deadline expires; independent engine inventory confirms removal |
| Unavailable engine | `error` | Image loading fails against the intentionally nonexistent socket |

All cases check only their intended source mutations, preserve their invocation
definition, and independently query Docker for leftover test containers. The
positive cases bind the inline comparison oracle to the authored baseline and
the executed archive to the recorded SHA-256. Final checks confirm the same
image, unchanged source, and unchanged archive. No prior result is rewritten.

The local regression suite passed **64/64** tests
([log](macos-regression.txt)). Linux ran the same 64 tests: **61 passed and three
optional NIfTI tests were skipped** because nibabel was not installed
([log](linux-regression.txt)). The emitted 12-node graph has zero schema errors
and six advisory source-dataset warnings ([validation](validation.txt)). No
`produced-by` edges were invented for those source datasets.

The canonical FSL workflow was not rerun. The clean core checkout does not carry
its generated `rokb` index, so an initial validation attempt there could not run.
This PR changes neither that workflow nor the core runner/schema.

## Environment and reproducibility boundary

The live run used Ubuntu 24.04.4 on ARM64, Docker 29.2.1 with its containerd image
store, DataLad 1.8.0, datalad-container 1.2.6 and PyYAML 6.0.3. Full versions are
in the summary, package list and [environment record](environment.txt).

The Docker image archive is SHA-256
`e2ab69a46c792c843015e9e17888fe8b062af8a482cb9bee14da0093a8a89854`.
Its executed image ID is
`sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`.
The actual annex key is recorded in the environment file; Glimmer separately
checks the SHA-256 of the complete archive. DataLad selected an MD5E annex key,
so the helper's local backend preference is not evidence of an SHA256E annex.

The disposable Colima profile had 2 CPUs, 3 GiB memory and a 10 GiB data disk,
with `--mount none --activate=false --ssh-config=false --ssh-agent=false
--port-forwarder none`. The sole observed host filesystem mount was Colima's
read-only image cache. No user home/project mount or agent credential entered
the VM. The worker was UID 501 and controlled its own disposable Docker daemon.

Operationally, the source was transferred as a Git bundle and cloned inside the
VM at the tested commit. The fixture itself copies verified source files from
that clean checkout into a DataLad template; its per-case datasets are fresh
DataLad clones. These are distinct operations. The driver checks Git state and
the installed CLI/runner bytes before and after the live run.

The container had no network, a read-only root and code/input mounts, only one
writable output mount, no capabilities, no new privileges, a nonroot UID,
128 MiB memory, 0.5 CPU, 64 processes, a 16 MiB temporary filesystem and a
15-second method deadline. Receipts record actual engine configuration and
write/visibility probes. This does not establish resistance to kernel escapes
or resource-exhaustion attacks. The validator, DataLad and Docker helper remain
trusted host processes. Prior image state is recorded per attempt. These checks do not qualify a
general cold-cache import path or independent-machine reproduction.

## Audit and retention

[Claude's initial audit](claude-initial-audit.json) found gaps in source identity,
failure-cause assertions, explicit tolerance, archive/oracle binding and cleanup
evidence. They were corrected and regression-tested.
[The closure audit](claude-closure-audit.json) reports no unresolved material
findings, conditional on the final live matrix passing. The retained result
satisfies its stated conditions: `phase=complete`, `passed=true`, 13 passing
cases, and all three final checks true. Claude performed static review only;
the observed execution evidence was produced by this qualification run.

After the first audited run, GitHub CI found a Python 3.10 incompatibility in
the hashing API and a signal-enum assertion. Both were corrected. The
[narrow compatibility audit](claude-compatibility-audit.json) accepts the
streaming SHA-256 change; its remaining import and signal-format conditions
are present in the source and exercised by the tests. The
[Python 3.10 and 3.12 CI jobs](ci.json) passed, including installed-CLI smoke
tests. All 13 live cases were then repeated successfully at the final source
commit listed above in a fresh VM using the retained image archive.

Before deleting the final VM, the exact image, Glimmer source Git bundle, template and
all case Git bundles, and evidence were retained in private local Glimmer
acceptance storage. The 44,016,474-byte payload's SHA-256 is
`f2cd950f845041a37ad8d16c65849b4db83c977c768024f467361a7b368f8351`;
all 267 contained file hashes were verified. That local copy is not a hosted
archive or a demonstrated restore service. The small Git review bundle alone
does not contain the image required to recover annex content.

The disposable profiles were removed after retention. The user's existing default
Colima profile remained stopped and unchanged.

Live identity/provider authentication, hosted run persistence, credential and
project isolation, reviewed derivative acceptance, archival recovery, schema
lifecycle changes and scientific evaluation remain separate open gates.
