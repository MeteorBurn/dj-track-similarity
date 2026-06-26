# Text search with CLAP

Audience: UI and CLI users  
Goal: search by describing sound in words  
Type: how-to

CLAP text search compares a written prompt with stored CLAP audio embeddings.
It is useful for rough sonic direction: scene, drums, bass, texture,
instruments, space, and vocal presence.

## Requirement

Run CLAP audio analysis first:

```powershell
dj-sim analyze --models clap --db .\data\library.sqlite
```

## Write a prompt

Prefer concrete audio language:

```text
dark hypnotic techno, rolling bass, dry percussion, no vocals
```

Avoid relying only on abstract mood words. CLAP does not know your DJ context;
it ranks by model similarity.

## Search from the UI

Open the `CLAP` tab, choose or type a prompt, optionally add a negative prompt,
then run `CLAP search`.

## Search from CLI

```powershell
dj-sim text-search "dark hypnotic techno, rolling bass, no vocals" `
  --limit 25 `
  --db .\data\library.sqlite
```

Expected result:

```text
<score>    <track_id>    <path>
```

Review matches manually before adding them to a set.
