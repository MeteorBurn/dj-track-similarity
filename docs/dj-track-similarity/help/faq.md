# FAQ

> Audience: Users wanting short answers.
> Goal: Answer common questions without reference-level detail.
> Type: explanation

## Does analysis change audio?

No. Analysis writes SQLite state. Explicit exceptions are genre tag apply, audio repair `--apply`, and Audio Dedup apply/delete.

## Should I trust the top result?

No. Treat scores as a shortlist and preview by ear.

## How do I analyze the whole library from CLI?

```powershell
dj-sim analyze --models sonara,maest,mert,clap --db <library-db>
```

## Can I share reports?

Only after checking paths, track names, and notes for private information.
