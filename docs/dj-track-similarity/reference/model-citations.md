# Model citations and licenses

> Audience: Users and maintainers checking upstream model and tool sources.
> Goal: Name the current upstream sources, checkpoints, and license notes.
> Type: reference

This page lists the optional upstream analysis tools and checkpoints used by the current adapters. It is based on `pyproject.toml`, `sonara_features.py`, `genres.py`, and `embedding.py`.

Because the project does not vendor or redistribute upstream model weights, this page gives attribution and practical license notes rather than legal advice. Optional packages download or load those assets when you run analysis. Check the upstream repositories and model cards before redistribution, hosted service use, commercial use, or published research.

## Current upstream sources

| Analysis family | Current code path | Upstream source | License note |
| --- | --- | --- | --- |
| SONARA | `sonara==0.2.4`, schema 3, playlist mode with BPM range `79.0..192.0`; exact provenance is stored per track | [kkollsga/sonara](https://github.com/kkollsga/sonara), [v0.2.4 release](https://github.com/kkollsga/sonara/releases/tag/v0.2.4) | Upstream is MIT. Preserve its license and check terms before redistribution. |
| MAEST | `discogs-maest-30s-pw-129e-519l` via `maest-infer` | [openmirlab/maest-infer](https://github.com/openmirlab/maest-infer), original [palonso/MAEST](https://github.com/palonso/MAEST) | `maest-infer` is AGPL-3.0-only and asks research users to cite the original MAEST paper. |
| MERT | `m-a-p/MERT-v1-95M` through Hugging Face Transformers | [yizhilll/MERT](https://github.com/yizhilll/MERT), [MERT-v1-95M checkpoint](https://huggingface.co/m-a-p/MERT-v1-95M) | GitHub code is Apache-2.0. The checkpoint page is marked CC-BY-NC-4.0. |
| MuQ | `OpenMuQ/MuQ-large-msd-iter` through the `muq` package | [tencent-ailab/muq](https://github.com/tencent-ailab/muq), [MuQ-large-msd-iter checkpoint](https://huggingface.co/OpenMuQ/MuQ-large-msd-iter) | Upstream code is MIT. Released MuQ weights are CC-BY-NC-4.0. |
| CLAP | LAION CLAP with `lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt` | [LAION-AI/CLAP](https://github.com/LAION-AI/CLAP), [checkpoint file](https://huggingface.co/lukewys/laion_clap/blob/main/music_audioset_epoch_15_esc_90.14.pt) | LAION CLAP code is Apache-2.0. The checkpoint listing is marked CC0-1.0. |

On Windows x64, `pyproject.toml` installs the project-published wheel from the
[MeteorBurn v0.2.4 release](https://github.com/MeteorBurn/sonara/releases/tag/v0.2.4), pinned with
SHA-256 `2dd2c39e106f7d5ca2fef9ca09e4de163469ec7ebe173c5e5ab6019c5284019d`. This is a packaging
location, not the upstream source repository. Other platforms resolve `sonara==0.2.4` from PyPI.

## Practical rules

- Treat upstream code licenses and model-weight licenses separately when the upstream project separates them.
- Do not treat this table as permission for commercial use. Non-commercial checkpoint licenses need their own review.
- If you publish research or public evaluation results, cite the upstream papers or project pages requested by the model authors.
- Local embeddings, labels, classifier artifacts, reports, and logs may reveal library information. Keep them out of Git unless you intentionally choose otherwise.

## Local classifier note

Rhythm Lab classifiers are local artifacts trained from your labels and existing library signals. They are not a downloaded upstream model family. Their outputs still depend on upstream SONARA, MAEST, and MERT inputs when those inputs are used for training or scoring.
