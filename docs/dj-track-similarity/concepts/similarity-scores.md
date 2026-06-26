# Similarity scores

Audience: users reading ranked results  
Goal: explain what scores can and cannot mean  
Type: explanation

Similarity scores are ranking hints. They help sort candidates, but they are
not objective judgments of musical quality or transition success.

## Why scores differ

Different search modes answer different questions:

- SONARA compares analyzed feature rows.
- MERT compares audio embeddings from selected seeds.
- CLAP compares text prompts or CLAP signals against stored embeddings.
- CLASS uses promoted classifier probabilities.
- SET combines several signals and then orders a route with constraints.

The same track can rank differently across these modes.

## Do not compare every number directly

A high score in one mode is not automatically stronger than a lower-looking
score in another mode. Treat each result list in the context of its own search
method.

## Listen before exporting

Use scores to reduce the search space. Use your ears and DJ judgement to decide
whether the track actually belongs in the set or crate.
