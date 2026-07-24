import { defineConfig } from "vitepress";

type SidebarSection = { text: string; items: { text: string; link: string }[] };

const englishNav = [
  { text: "Home", link: "/" },
  { text: "Guide", link: "/project-guide.html" },
  { text: "Getting Started", link: "/getting-started/quickstart.html" },
  { text: "User Guide", link: "/user-guide/" },
  { text: "Reference", link: "/reference/" }
];

const russianNav = [
  { text: "Главная", link: "/ru/" },
  { text: "Карта документации", link: "/ru/project-guide.html" },
  { text: "Первые шаги", link: "/ru/getting-started/quickstart.html" },
  { text: "Руководство", link: "/ru/user-guide/" },
  { text: "Справочник", link: "/ru/reference/" }
];

const englishSidebar: SidebarSection[] = [
  { text: "Start", items: [{ text: "Home", link: "/" }, { text: "Project guide", link: "/project-guide.html" }] },
  { text: "Getting started", items: [{ text: "Overview", link: "/getting-started/" }, { text: "Quickstart", link: "/getting-started/quickstart.html" }, { text: "Install", link: "/getting-started/install.html" }, { text: "First library", link: "/getting-started/first-library.html" }, { text: "First analysis", link: "/getting-started/first-analysis.html" }] },
  { text: "User guide", items: [{ text: "Overview", link: "/user-guide/" }, { text: "Browse library", link: "/user-guide/browse-library.html" }, { text: "Analyze library", link: "/user-guide/analyze-library.html" }, { text: "Search with seeds", link: "/user-guide/search-with-seeds.html" }, { text: "Smart Set Builder", link: "/user-guide/smart-set-builder.html" }, { text: "Text search", link: "/user-guide/text-search.html" }, { text: "CLASS tab", link: "/user-guide/class-tab.html" }, { text: "Export playlists", link: "/user-guide/export-playlists.html" }, { text: "Tags and audio writes", link: "/user-guide/tags-and-audio-writes.html" }] },
  { text: "Workflows", items: [{ text: "Overview", link: "/workflows/" }, { text: "Prepare a set", link: "/workflows/prepare-a-set.html" }, { text: "Find compatible tracks", link: "/workflows/find-compatible-tracks.html" }, { text: "Build crates", link: "/workflows/build-crates.html" }, { text: "Train classifier", link: "/workflows/train-personal-classifier.html" }, { text: "Reanalyze split SONARA storage", link: "/workflows/reanalyze-sonara-split-storage.html" }, { text: "Maintain library", link: "/workflows/maintain-library.html" }] },
  { text: "Concepts", items: [{ text: "Overview", link: "/concepts/" }, { text: "Project idea", link: "/concepts/project-idea.html" }, { text: "Local-first safety", link: "/concepts/local-first-safety.html" }, { text: "Features, embeddings, tags", link: "/concepts/features-embeddings-tags.html" }, { text: "Similarity scores", link: "/concepts/similarity-scores.html" }, { text: "SET routing", link: "/concepts/smart-set-builder-routing.html" }, { text: "Classifiers and Rhythm Lab", link: "/concepts/classifiers-and-rhythm-lab.html" }] },
  { text: "Tools and scripts", items: [{ text: "Overview", link: "/tools-and-scripts/" }, { text: "Rhythm Lab", link: "/tools-and-scripts/rhythm-lab.html" }, { text: "Audio Dedup", link: "/tools-and-scripts/audio-dedup.html" }, { text: "Audio Doctor", link: "/tools-and-scripts/audio-doctor.html" }, { text: "Persistent ANN indexes", link: "/tools-and-scripts/persistent-ann-indexes.html" }, { text: "Optimize database", link: "/tools-and-scripts/optimize-database.html" }] },
  { text: "Reference", items: [{ text: "Overview", link: "/reference/" }, { text: "CLI", link: "/reference/cli.html" }, { text: "API", link: "/reference/api.html" }, { text: "Database", link: "/reference/database.html" }, { text: "Configuration", link: "/reference/configuration.html" }, { text: "Analysis families", link: "/reference/analysis-families.html" }, { text: "SONARA v0.3.1 contract", link: "/reference/sonara-v0-3-1-contract.html" }, { text: "Model citations", link: "/reference/model-citations.html" }, { text: "UI controls", link: "/reference/ui-controls.html" }] },
  { text: "Developer", items: [{ text: "Overview", link: "/developer/" }, { text: "Architecture", link: "/developer/architecture.html" }, { text: "Development", link: "/developer/development.html" }, { text: "Testing", link: "/developer/testing-and-verification.html" }, { text: "Release checklist", link: "/developer/release-checklist.html" }] },
  { text: "Help", items: [{ text: "Overview", link: "/help/" }, { text: "Troubleshooting", link: "/help/troubleshooting.html" }, { text: "FAQ", link: "/help/faq.html" }, { text: "Known limits", link: "/help/known-limits.html" }] }
];

const russianSectionLabels: Record<string, string> = {
  Start: "Начало",
  "Getting started": "Первые шаги",
  "User guide": "Руководство пользователя",
  Workflows: "Сценарии",
  Concepts: "Основные понятия",
  "Tools and scripts": "Инструменты и скрипты",
  Reference: "Справочник",
  Developer: "Разработчику",
  Help: "Помощь"
};

const russianItemLabels: Record<string, string> = {
  Home: "Главная",
  "Project guide": "Карта документации",
  Overview: "Обзор",
  Quickstart: "Быстрый старт",
  Install: "Установка",
  "First library": "Первая библиотека",
  "First analysis": "Первый анализ",
  "Browse library": "Просмотр библиотеки",
  "Analyze library": "Анализ библиотеки",
  "Search with seeds": "Поиск по опорным трекам",
  "Smart Set Builder": "Smart Set Builder",
  "Text search": "Текстовый поиск",
  "CLASS tab": "Вкладка CLASS",
  "Export playlists": "Экспорт плейлистов",
  "Tags and audio writes": "Теги и запись в аудиофайлы",
  "Prepare a set": "Подготовка сета",
  "Find compatible tracks": "Поиск совместимых треков",
  "Build crates": "Создание подборок",
  "Train classifier": "Обучение классификатора",
  "Reanalyze split SONARA storage": "Повторный анализ SONARA",
  "Maintain library": "Обслуживание библиотеки",
  "Project idea": "Идея проекта",
  "Local-first safety": "Локальная работа и безопасность",
  "Features, embeddings, tags": "Признаки, эмбеддинги и теги",
  "Similarity scores": "Оценки сходства",
  "SET routing": "Построение маршрута SET",
  "Classifiers and Rhythm Lab": "Классификаторы и Rhythm Lab",
  "Rhythm Lab": "Rhythm Lab",
  "Audio Dedup": "Audio Dedup",
  "Audio Doctor": "Audio Doctor",
  "Persistent ANN indexes": "Постоянные индексы ANN",
  "Optimize database": "Оптимизация базы данных",
  CLI: "CLI",
  API: "API",
  Database: "База данных",
  Configuration: "Конфигурация",
  "Analysis families": "Семейства анализа",
  "SONARA v0.3.1 contract": "Контракт SONARA v0.3.1",
  "Model citations": "Модели и лицензии",
  "UI controls": "Элементы интерфейса",
  Architecture: "Архитектура",
  Development: "Разработка",
  Testing: "Тестирование",
  "Release checklist": "Проверка релиза",
  Troubleshooting: "Решение проблем",
  FAQ: "Частые вопросы",
  "Known limits": "Известные ограничения"
};

function russianLink(link: string): string {
  return link === "/" ? "/ru/" : `/ru${link}`;
}

const russianSidebar: SidebarSection[] = englishSidebar.map((section) => ({
  text: russianSectionLabels[section.text] ?? section.text,
  items: section.items.map((item) => ({
    text: russianItemLabels[item.text] ?? item.text,
    link: russianLink(item.link)
  }))
}));

const localSearch = {
  provider: "local" as const,
  options: {
    locales: {
      ru: {
        translations: {
          button: {
            buttonText: "Поиск",
            buttonAriaLabel: "Поиск по документации"
          },
          modal: {
            displayDetails: "Показать подробный список",
            resetButtonTitle: "Сбросить поиск",
            backButtonTitle: "Закрыть поиск",
            noResultsText: "Ничего не найдено по запросу",
            footer: {
              selectText: "выбрать",
              navigateText: "перейти",
              closeText: "закрыть"
            }
          }
        }
      }
    }
  }
};

const commonTheme = {
  siteTitle: "DJ Track Similarity Docs",
  logo: { light: "/logo-light.svg", dark: "/logo-dark.svg", alt: "DJ Track Similarity" },
  socialLinks: [{ icon: "github", link: "https://github.com/MeteorBurn/dj-track-similarity" }],
  search: localSearch
};

export default defineConfig({
  title: "dj-track-similarity",
  description: "Human-oriented documentation for local DJ track similarity workflows.",
  lang: "en-US",
  base: "/docs/",
  head: [["link", { rel: "icon", type: "image/svg+xml", href: "/docs/favicon.svg" }]],
  outDir: "site",
  cleanUrls: false,
  appearance: true,
  lastUpdated: true,
  themeConfig: {
    ...commonTheme,
    nav: englishNav,
    sidebar: englishSidebar,
    outline: { level: [2, 3], label: "On this page" },
    docFooter: { prev: "Previous", next: "Next" },
    footer: {
      message: "Local-first DJ library analysis documentation.",
      copyright: "Public personal utility documentation."
    }
  },
  locales: {
    root: {
      label: "English",
      lang: "en-US",
      title: "dj-track-similarity",
      description: "Human-oriented documentation for local DJ track similarity workflows.",
      themeConfig: {
        ...commonTheme,
        nav: englishNav,
        sidebar: englishSidebar,
        outline: { level: [2, 3], label: "On this page" },
        docFooter: { prev: "Previous", next: "Next" },
        footer: {
          message: "Local-first DJ library analysis documentation.",
          copyright: "Public personal utility documentation."
        }
      }
    },
    ru: {
      label: "Русский",
      lang: "ru-RU",
      link: "/ru/",
      title: "dj-track-similarity",
      description: "Практическая документация по локальному анализу музыкальной библиотеки для диджея.",
      themeConfig: {
        ...commonTheme,
        siteTitle: "Документация DJ Track Similarity",
        nav: russianNav,
        sidebar: russianSidebar,
        outline: { level: [2, 3], label: "На этой странице" },
        docFooter: { prev: "Назад", next: "Далее" },
        lastUpdated: { text: "Обновлено" },
        darkModeSwitchLabel: "Оформление",
        lightModeSwitchTitle: "Включить светлую тему",
        darkModeSwitchTitle: "Включить тёмную тему",
        sidebarMenuLabel: "Меню",
        returnToTopLabel: "Наверх",
        langMenuLabel: "Язык",
        skipToContentLabel: "Перейти к содержанию",
        notFound: {
          title: "СТРАНИЦА НЕ НАЙДЕНА",
          quote: "Такого адреса в документации нет.",
          linkLabel: "перейти на главную",
          linkText: "На главную"
        },
        footer: {
          message: "Документация локального инструмента анализа музыкальной библиотеки.",
          copyright: "Публичная документация личного проекта."
        }
      }
    }
  }
});
