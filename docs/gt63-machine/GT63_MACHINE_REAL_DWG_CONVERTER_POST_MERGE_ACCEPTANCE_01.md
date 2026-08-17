# GT63 MACHINE — Real DWG Converter Post-Merge Acceptance #01

**Status:** PASS — ACCEPTED  
**Repository:** `goceterziev-creator/ZURU-BIM-Analyzer`  
**Capability:** Real DWG Converter Integration v1  
**Source PR:** #13  
**Accepted merge commit:** `49b5e7f650f7964793c23f3689430bfb059d4a5a`  
**Accepted PR head:** `4264697d6e0597dc575d63d6935f07a223bf5a7f`  
**Pinned LibreDWG revision:** `318a874db260fdb6ee9208ea8ab445772caab72e`

## Acceptance purpose

Close the post-merge gate for Real DWG Converter Integration v1 and record the exact accepted capability and its boundaries in `main`.

This document does not broaden the accepted product scope and does not claim native DWG semantic analysis.

## Accepted evidence chain

The delivery passed the required sequence:

`Executor → Evidence → Canonical Tests → Exact-Head CI → MACHINE Review → Human Gate → Merge`

Final pre-merge evidence:

- canonical test discovery executed 33 tests successfully;
- the LibreDWG pin regression tests were visibly included in canonical discovery;
- exact PR head CI passed;
- MACHINE independently reviewed the exact candidate and issued `APPROVE`;
- explicit Human Gate authorization was received for PR #13;
- PR #13 was merged without changing the accepted head candidate.

## Merge identity

The accepted merge commit is:

`49b5e7f650f7964793c23f3689430bfb059d4a5a`

The merge commit has two parents:

- prior `main`: `17717ee27ef7ad4cf86c2a6b391d466b75b8a15f`
- accepted PR head: `4264697d6e0597dc575d63d6935f07a223bf5a7f`

GitHub reports the merge commit signature as verified.

## Accepted capability

ZURU now has a production LibreDWG-backed DWG→DXF converter adapter integrated behind the existing DWG ingestion boundary.

Accepted flow:

`DWG input → LibreDWG converter adapter → DXF bytes → canonical analyze_dxf_bytes() → normalized evidence/result`

DXF remains on the existing canonical direct analysis path.

The converter:

- uses an explicit subprocess boundary rather than claiming native DWG parsing;
- uses temporary conversion workspace and deterministic cleanup;
- invokes subprocesses with argv lists rather than shell filename interpolation;
- applies a bounded conversion timeout;
- rejects missing or empty conversion output;
- validates produced DXF through the canonical ZURU DXF analyzer before returning it;
- preserves ingestion/conversion provenance separately from normalized DXF evidence.

## Dependency identity acceptance

LibreDWG is pinned to the immutable reviewed revision:

`318a874db260fdb6ee9208ea8ab445772caab72e`

Bootstrap must fetch and checkout that exact revision.

A cached `dwg2dxf` binary is reusable only when its recorded `upstream_commit` provenance equals the currently reviewed pin. Missing or mismatched cache provenance invalidates the cache and requires a fresh pinned build.

This closes the earlier non-deterministic moving-upstream dependency blocker.

## Regression acceptance

The final canonical suite includes regression coverage for:

- exact pinned LibreDWG checkout;
- rejection of invalid or drifting pin identity;
- reuse of a matching provenance-bound cached binary;
- rejection/rebuild behavior for a mismatched cached binary;
- real converter subprocess behavior;
- conversion timeout/failure behavior;
- empty-output rejection;
- canonical DXF validation of converted output;
- existing DWG ingestion boundary behavior;
- existing ZURU DXF regressions.

Final canonical discovery result before merge:

**33 tests — PASS**

## Real-file evidence

The development/validation sequence used the genuine `Sana fasadi.dwg` input and demonstrated a real LibreDWG `dwg2dxf` execution producing non-empty DXF which ZURU successfully routed through canonical ingestion.

Generated conversion artifacts were not accepted into the delivery branch.

This real-file evidence demonstrates the bounded conversion/ingestion path; it does not establish universal DWG compatibility or semantic correctness for every DWG producer/version.

## Boundaries that remain in force

This acceptance does **not** prove or authorize:

- native DWG semantic analysis inside ZURU;
- universal compatibility with arbitrary DWG files or versions;
- semantic BIM correctness of all converted content;
- unrestricted runtime network/build authority in every deployment environment;
- redistribution of LibreDWG binaries without separate licensing review;
- removal of the MACHINE Review Gate;
- autonomous merge authority.

## Governance result

The experiment reinforced the mandatory delivery rule:

> **GREEN CI ≠ MACHINE APPROVAL.**

PR #13 produced multiple green automated signals before all architectural and evidence blockers were closed. Independent MACHINE review detected those blockers, required bounded corrections, and only then issued approval.

The accepted gate remains:

`Executor → Evidence → Tests → CI → MACHINE Review → Human Gate → Merge`

## Post-merge verification note

The merge identity has been verified directly in `main`. The available commit-workflow lookup exposes pull-request-triggered runs only and therefore does not provide a separate post-merge `main` workflow result for this merge commit. Post-merge acceptance therefore relies on the unchanged accepted PR head, exact-head canonical CI, MACHINE approval, explicit Human Gate, and verified merge identity; it does not falsely claim an additional post-merge CI run.

## Final verdict

**PASS — REAL_DWG_CONVERTER_INTEGRATION_V1_ACCEPTED**

Real DWG Converter Integration v1 is now an accepted capability of ZURU `main` at merge commit `49b5e7f650f7964793c23f3689430bfb059d4a5a`, within the boundaries recorded above.
