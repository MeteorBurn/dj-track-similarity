# Frontend v7 Port — Acceptance Criteria

## 16. Критерии приёмки

Goal можно отметить complete только когда:

1. Основной React UI использует актуальный v7 API contract без активных legacy Track consumers.
2. `api.ts`, `apiClient.ts`, backend schemas/routes и tests согласованы.
3. SONARA использует `core`, `timeline`, `embedding`, `fingerprint`, а не `representations`.
4. MuQ штатно присутствует во всех применимых frontend model/source/readiness/breakdown consumers наравне с MERT, MAEST и CLAP; stale-текст “без поиска и SET” удалён.
5. Отдельная MUQ tab использует generic search с `analysis_family="muq"` и корректно показывает current/missing/stale состояния.
6. LAB показывает самостоятельную MuQ candidate group либо model-scoped unavailable reason и сохраняет verdict с `model="muq"`.
7. Внешний раздел SET содержит две удобные вложенные вкладки `Set Builder` и `Hybrid Preview`; endpoint, payload, score semantics, loading/error/results и stale guards не смешаны.
8. `Add preview` работает только с актуальным SET Builder response и никогда не добавляет MERT/MuQ/SONARA/CLAP или Hybrid results.
9. SET, Hybrid и Audio Dedup UI поддерживают MuQ source/toggle/weight, показывают фактические backend `sources`/`weights_used` или status weights и сохраняют проверяемый MuQ-disabled legacy profile.
10. Standalone Rhythm Lab UI работает с текущими v7 identities, показывает MuQ feature status и не оставляет закрытые source/feature lists без MuQ.
11. Audio Dedup остаётся dry-run-first; UI не ослабляет `APPLY DELETE`, root/identity/file-state gates и не изображает MuQ как самостоятельное основание удаления.
12. В `Библиотека и прослушивание` доступны 100/500/1000/Все.
13. 1000/Все загружаются bounded chunks, поддерживают progress/cancel и не создают stale-state race.
14. Несколько тысяч треков не превращаются в несколько тысяч тяжёлых одновременно отрисованных DOM-узлов.
15. UI слегка улучшен; основной tab strip и вложенные SET tabs доступны, адаптивны и не ломают существующие сценарии или визуальную систему.
16. SQLite-изменения подкреплены query plan и before/after измерениями.
17. Schema v7, таблица `muq_embeddings`, database identity topology и реальные БД/аудиофайлы не изменены.
18. Frontend typecheck/test/build зелёные либо каждый pre-existing unrelated failure отдельно доказан и явно сообщён.
19. Focused backend и Rhythm Lab tests зелёные.
20. Browser smoke выполнен без console/API ошибок на desktop и узком окне.
21. `git diff --check` проходит.
22. Несвязанные пользовательские изменения сохранены.
23. Generated/local files не добавлены в Git.
24. Документация EN/RU обновлена, если поведение изменилось.
