# Choosing & Wiring Your Data Store

> Glimmer is **storage-agnostic**. This recipe is opinionated about the *pattern* — a DataLad
> superdataset with a git-annex **special remote**, where compute pulls only the working subset — and
> deliberately **open about the provider**. Pick the backend that fits your budget, durability,
> locality, and compliance constraints. The reference project's choice is shown as *one* worked
> example, not a mandate.

See [`datalad-pattern.md`](datalad-pattern.md) for *how* the graph and the file tree compose. This doc
is about *where the bytes live*.

## The one rule: separate the bulk store from the compute working set

Scientific data (raw + derivatives) outgrows any single machine, and derivatives balloon during analysis.
The pattern that scales — and that Glimmer's `datalad-*` node fields are built for:

```
   ┌─────────────────────────┐         datalad get <subset>      ┌──────────────────────┐
   │  BULK STORE (cheap,      │  ───────────────────────────────▶ │  COMPUTE NODE        │
   │  always-on, durable)     │                                    │  (NVMe scratch)      │
   │  = git-annex special     │  ◀─────────────────────────────── │  run pipeline,       │
   │    remote: the WHOLE     │         datalad push <derivs>      │  datalad push,       │
   │    annex (raw+derivs)    │                                    │  datalad drop        │
   └─────────────────────────┘                                    └──────────────────────┘
```

- **Bulk store** holds the full content-addressed annex. Optimize for €/TB and durability, *not* IOPS.
- **Compute node** never holds the whole dataset — it `datalad get`s the subjects/files it's processing,
  runs, `datalad push`es derivatives back, and `datalad drop`s to free scratch. Latency to the bulk
  store matters, so co-locate them (same region / same datacenter) when you can.

This keeps storage cheap (you pay bulk rates for everything, block/SSD rates only for the live subset)
and makes every analysis reproducible from the graph: `datalad install <super>; datalad get <path>`.

## Pick a backend — a decision aid (not a verdict)

git-annex speaks many backends through **special remotes**; DataLad rides on top. Evaluate against *your*
constraints:

| Backend | €/TB·mo (rough) | Always-on | Egress | Compute-local? | Good when… |
|---|---|---|---|---|---|
| **Local NAS / disk** | one-time HW | you maintain it | none | yes (if compute is local) | you have a reliable always-on box + backups; data sovereignty |
| **Institutional NAS / HPC** | free-ish | dept-run | none on-net | yes (on the cluster) | active institutional affiliation + the data may live there already |
| **Object storage** (S3 / B2 / GCS / R2 / MinIO) | ~$5–23 | ✅ | varies (B2/R2 low) | no (network) | provider-agnostic, scales infinitely, pairs with any cloud compute |
| **Managed network store** (e.g. Hetzner Storage Box) | ~€2 | ✅ | free | no (network, free intra-DC) | cheapest always-on bulk; SFTP/rsync/Samba; pairs with same-provider compute |
| **Consumer cloud** (Google Drive / Dropbox via `rclone`) | bundled | ✅ | quota-limited | no | small projects, already-paid quota, light derivatives |

Cross-cutting checks before you commit:
- **Compliance / PHI.** If the data is human-subjects, the store must satisfy your IRB/DUA (encryption at
  rest, access control, region). Keep identified data *out of the committed graph* regardless of backend
  (commit de-identified metadata + content hashes; see [`agent-protocol.md`](agent-protocol.md)).
- **Durability & backup.** A single drive or a single bucket is not a backup. Use snapshots / a second
  region / `datalad push` to a second remote for anything you can't regenerate.
- **Egress.** Repeated `datalad get` over a metered link adds up — favor low/no-egress backends or
  co-locate compute with the store.
- **Exit cost.** Object storage and DataLad both keep you portable; avoid backends you can't `git annex
  copy --to` out of.

## Wiring a special remote (generic)

git-annex is the common denominator. Two idioms cover almost everything:

**SSH/rsync remote** (NAS, Storage Box, any SSH host):
```bash
git annex initremote store type=rsync rsyncurl=user@host:/path/annex encryption=none
# or with client-side encryption:
git annex initremote store type=rsync rsyncurl=... encryption=shared
datalad push --to store
```

**rclone remote** (S3, B2, GCS, R2, Drive, … — one config, dozens of providers):
```bash
rclone config                      # define a remote, e.g. "b2:" or "s3:" or "gdrive:"
git annex initremote store type=external externaltype=rclone target=b2 prefix=ads-annex encryption=shared
datalad push --to store
```

Then the pull-only-the-working-set loop on the compute node:
```bash
datalad clone <superdataset-url> proj && cd proj
datalad get sub-XYZ                 # fetch only what you're analyzing
datalad run -m "fmriprep sub-XYZ" <cmd>   # provenance captured → Glimmer method/derivative nodes
datalad push --to store             # derivatives back to the bulk store
datalad drop sub-XYZ                # free scratch
```

## Worked example (the reference project's choice — pick your own)

The ADS reference deployment uses a **Hetzner Storage Box (BX31, 10 TB, ~€21/mo, Helsinki)** as the bulk
git-annex remote, co-located with cloud compute in the same region (free intra-datacenter traffic),
provisioned from the CLI:
```bash
hcloud storage-box create --name <name> --type bx31 --location hel1 \
  --password "$PW" --enable-ssh --enable-samba --enable-zfs --reachable-externally --ssh-key "$PUBKEY"
# then add as an rsync special remote over SSH (passwordless via the attached key)
```
This was chosen for €/TB + always-on + same-region compute. **Your constraints may point elsewhere** — an
institutional HPC allocation, a B2 bucket, or a NAS you already run are all first-class. The Glimmer
schema's `datalad-superdataset` / `datalad-relative-path` / `datalad-commit-sha` / `datalad-annex-key`
fields make the graph re-fetchable regardless of which backend you land on.

## Anti-patterns
- **Committing large files to git** (not annex) — bloats the repo, breaks the whole-graph SHA. Let
  git-annex/DataLad handle every byte an analysis depends on.
- **One copy = your only copy.** Always have a second remote or snapshots for non-regenerable data.
- **Hoarding intermediates.** Push final derivatives; drop pipeline workdirs (or keep them in a
  separate, droppable sub-dataset).
- **Backend lock-in.** If you can't `git annex copy --to` your data elsewhere, you've coupled too tightly.
