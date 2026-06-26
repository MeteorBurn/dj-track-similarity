# First analysis

Аудитория: новые пользователи  
Цель: выбрать первый безопасный analysis pass  
Тип: tutorial

Не обязательно анализировать всю библиотеку сразу. Начните с маленького limit и
одной analysis family.

## 1. Активировать окружение

```powershell
.\.venv\Scripts\Activate.ps1
```

Все следующие команды предполагают активное окружение.

## 2. Начать с SONARA

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

SONARA дает feature-oriented search surface и относительно понятные stored
features.

## 3. Добавлять embeddings по необходимости

```powershell
dj-sim analyze --models mert --limit 25 --db .\data\library.sqlite
dj-sim analyze --models clap --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest --limit 25 --db .\data\library.sqlite
```

MERT нужен для seed similarity, CLAP для text search, MAEST для genre analysis
и MAEST embeddings.

## 4. Whole library mode

`--limit 0` означает всю библиотеку для missing results выбранной family.
Используйте это только когда уверены в setup и времени выполнения.

## 5. Device

`--device auto` выбирает CUDA, если PyTorch видит GPU, иначе CPU. Явное
`--device cuda` должно ошибиться, если CUDA недоступна.
