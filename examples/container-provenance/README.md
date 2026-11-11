# A real container execution and fresh replay

This example runs one synthetic calculation through the installed Glimmer CLI,
DataLad, git-annex, and Docker. It tests the existing runner without changing the
core schema or introducing a hosted execution service.

Four authored inputs, `[2,4,6,8]`, produce a count of 4, sum of 20, and mean of 5.
The expected JSON is committed before any run. It is never mounted inside the
computation container or updated from observed output.

## Run on a disposable Linux Docker host

Use a fresh VM with no production credentials, home-directory mounts, SSH-agent
forwarding, or other workloads. The worker must be a nonroot user with permission
to control that VM's Docker daemon. Docker access is privileged host authority;
this is a trusted test worker, not a sandbox for arbitrary uploaded code.

Requirements: Python 3.11+, Git, git-annex, and Docker. The recorded live test uses
Ubuntu 24.04, Python 3.12, and ARM64. Other platforms require their own run.

From a fresh, clean Git checkout containing this example (including no ignored
cache files in the checked source paths):

```bash
python3 -m venv /tmp/glimmer-container-venv
. /tmp/glimmer-container-venv/bin/activate
pip install -r examples/container-provenance/requirements.txt .

# Freeze the image version before exporting; execution never pulls a tag.
docker pull python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
docker tag python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b glimmer-fixture:qualified
docker save --output /tmp/glimmer-python.tar glimmer-fixture:qualified

# Synthetic outer-project bait for the container visibility check.
sudo mkdir -p /var/lib/glimmer-other-project
printf 'synthetic isolated project marker\n' | sudo tee /var/lib/glimmer-other-project/marker.txt

python examples/container-provenance/qualify.py \
  --work /var/tmp/glimmer-container-acceptance \
  --image-archive /tmp/glimmer-python.tar \
  --source-revision "$(git rev-parse HEAD)"
```

Use a new `--work` directory for each invocation. A Docker archive exported on
another engine or architecture may have a different SHA-256. The driver records
the exact archive hash, platform, immutable image ID, source file hashes,
dependency versions, and source revision used in that attempt.
The driver verifies that revision against Git and checks the installed CLI and
runner bytes against the checkout. Keep the virtual environment and generated
evidence outside the source checkout. Before destroying the VM, copy the image,
dataset histories, source, and evidence to storage you intend to retain; local
temporary paths do not provide archival durability.

## What the qualification does

The driver creates a DataLad dataset, saves the trusted method and validator in
Git, registers the image archive in git-annex, and emits a 12-node Markdown graph
using existing schema types and a local domain profile. Input data, method code,
validator code, container helper, registration configuration, and the authored
baseline are pinned to regular Git blobs at a full commit ID; the image uses an
actual annexed archive and its SHA-256. Validation may report advisory warnings for source
datasets without `produced-by` edges; schema errors stop the test.

Every case starts in a fresh clone with no output files. The first is a forward
execution (`executed`). The second is a replay against the authored baseline
(`checks-passed`): one raw-byte match and three numeric comparisons with zero
tolerance. A fresh clone and fresh container share the same VM and engine; this
is not an independent-machine reproduction.

Eleven negative cases reject changed, missing, or invalid input; an unavailable
validator; changed or missing image bytes; a failed command; a missing declared
output; an incorrect baseline; a timeout; and an unavailable Docker engine.
An expected rejection is a successful *test*, not a successful research run.
The driver also checks that the graph, baseline, and trusted source files were
not rewritten. It does not pass `--no-container`, `--no-gate`, or `--write-verdict`.
The actual comparison oracle is the run-record's inline copy of the baseline.
The positive cases cross-check that copy against the committed template and
pinned baseline file. Negative gate tests assert their specific failure cause,
and every case checks that only its intended paths were changed.

`<work>/evidence/` retains each definition, CLI log, Glimmer manifest, result
commit, DataLad run message, actual output, and container receipt. Receipts use
distinct IDs and exclusive file creation; they are ordinary local files, not
signed attestations or tamper-proof storage. `qualification.json` records the
overall result and exact checks. Preserve the dataset and image archive as well
if another machine must recover this exact attempt; the small evidence bundle
alone is insufficient to restore annex content.
Each attempt is hashed into the summary. Unexpected case failures produce a
failed receipt, and progress is saved after each case. The command supervisor
terminates the process group on a deadline; the helper handles SIGTERM and
removes containers by their reserved name even if creation loses its response.
The driver separately queries Docker after every case. Forced termination of
the VM or an uncatchable process kill still requires operator recovery.

## Container boundary and trust

DataLad supports a custom invocation through
[`containers-add --call-fmt`](https://docs.datalad.org/projects/container/en/stable/generated/man/datalad-containers-add.html).
This fixture registers one image **file**, as required by the current Glimmer
runner, and invokes `code/container_entry.py`. The default DataLad Docker adapter
uses an image directory and different mount policy; this example does not claim
to qualify that adapter or every Docker/Singularity registration.

The helper checks an archived immutable image identifier and starts Docker with:

- nonroot UID, read-only root, all capabilities dropped, no new privileges;
- read-only `code` and `inputs`, and one writable `out` directory;
- no network, credentials, Docker socket, or authored comparison baseline mount;
- 128 MiB memory, 0.5 CPU, 64-process limit, and a 16 MiB temporary filesystem;
- a 15-second command deadline followed by container removal, including failure.

The receipt records actual engine configuration and state. The method probes
write denial, UID, absent outer-project bait and Docker socket, absent baseline,
and a denied external connection. A failed connection alone is not isolation
proof; it is checked alongside Docker's `NetworkMode=none`. These probes do not
test every kernel escape or resource-exhaustion attack. Source/validator checks,
image loading, and DataLad run on the trusted worker outside the container.
The pinned base image is not a vulnerability scan or a publisher attestation.
OCI metadata must link the selected index/manifest to the archived configuration.
The receipt records whether an immutable image was already present in the
engine. Each computation uses a fresh container; this is not a cold-cache image
import test.

## Review boundary

```bash
python -m unittest discover -s tests -v
```

Unit tests cover archive handling and failure receipts; the command above is
not a substitute for the live qualification. The separate canonical FSL example
is unchanged and is not run by this fixture.

This example does not qualify the hosted run UI, credential isolation, Workbox
provider login, per-project authorization, reviewed derivative acceptance,
archive durability, or scientific validity. Those remain separate release
gates. It supplies a concrete computational path and inspectable evidence for
the app's future execution integration.
