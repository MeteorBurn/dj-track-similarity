# Prepare a set from a few anchors

> Audience: Users building an ordered listening candidate list.
> Goal: Move from seed tracks to export without treating the preview as final truth.
> Type: workflow

Use this workflow when you have a few tracks that define a direction but do not yet have a useful
route between them. The result is an editable sequence of candidates: enough structure to begin
rehearsing or crate preparation, without pretending the order is final.

## Browser and API entry points

The browser provides the complete workflow below. Direct clients can use `POST /api/search` or
`POST /api/search/sonara` to expand anchors, send chosen track IDs to
`POST /api/set-builder/generate`, audition candidates through `GET /media/{track_id}`, and send the
final IDs to `POST /api/export`. CLAP text search is also available through
`dj-sim text-search`. The current contracts are in the [API reference](../reference/api.md).

The browser's SET tab exposes the same source/weight fields in independent **Set Builder** and
**Hybrid Preview** tabs. Expect to remove, replace, and reorder tracks after listening.

## 1. Start with a scanned and analyzed library

For SET, run all core analysis families:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
dj-sim analyze --models maest,mert,muq,clap --db .\data\library.sqlite
```

The default SET request requires SONARA, MERT, MAEST, MuQ, and CLAP. For the exact pre-MuQ request,
select only `mert`, `maest`, and `clap` with raw weights `0.30`, `0.18`, `0.22`, plus SONARA broad
at `0.30`. MuQ is not loaded or required for eligibility, and the backend normalizes the selected
weights.

## 2. Pick anchors

In the library, search or page to tracks that represent the area you want. Add one to five seeds.

Avoid choosing two tracks from the same known artist for one SET preview. The backend enforces at most one track per known artist.

## 3. Generate a SET preview

Open the SET tab.

- Choose **Manual** if your selected seeds should be fixed anchors.
- Choose **Auto** if you want the app to choose anchors from the eligible library.
- Pick a set mode, energy curve, track limit, and diversity value.
- Keep the default MERT, MAEST, MuQ, and CLAP sources or choose an explicit subset.
- Use BPM trajectory only when you truly want the set to climb or descend.
- Use classifier preferences only when you understand the promoted classifier.

Click **Generate**. Review the coverage counts and preview order.

## 4. Check alternatives

Use MERT for a broad seed neighborhood. Use SONARA when you want to steer audible feature groups.
Use CLAP when you can describe a missing sound in words. Use Hybrid preview when you want to see
which model sources support a candidate and where transition risk may need attention. Hybrid
defaults to `mert`, `maest`, `muq`, `sonara`, and `clap` at `0.20` each.

## 5. Listen

Preview candidates by ear. Watch for:

- too many similar tracks,
- artist repetition,
- energy dips or jumps,
- vocal conflicts,
- key or tempo transitions that look fine numerically but feel wrong.

## 6. Add and export

Click **Add preview** only when the latest Set Builder preview is useful. The action does not append
Hybrid or another search tab's results. Then edit the current set manually and export M3U or CSV.

```mermaid
flowchart LR
    A[Seeds] --> B[SET preview]
    B --> C[Preview by ear]
    C --> D[Add preview]
    D --> E[Manual set edits]
    E --> F[Export M3U or CSV]
```

## Safety

SET generation is read-only. Adding preview changes only the browser's current set state. Export writes a new playlist file, not audio tags.
