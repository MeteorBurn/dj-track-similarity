# Similarity scores

Аудитория: пользователи ranked results  
Цель: объяснить, что могут и не могут значить scores  
Тип: explanation

Similarity scores - ranking hints. Они помогают сортировать candidates, но не
являются objective judgement of musical quality или transition success.

## Why scores differ

Разные search modes отвечают на разные вопросы:

- SONARA compares analyzed feature rows.
- MERT compares audio embeddings from selected seeds.
- CLAP compares text prompts or CLAP signals against stored embeddings.
- CLASS uses promoted classifier probabilities.
- SET combines several signals and then orders a route with constraints.

Один track может rank differently в разных modes.

## Do not compare every number directly

High score в одном mode не обязательно сильнее lower-looking score в другом
mode. Читайте result list в контексте его search method.

## Listen before exporting

Используйте scores, чтобы сузить search space. Решение о том, подходит ли track
в set или crate, принимайте ушами и DJ judgement.
