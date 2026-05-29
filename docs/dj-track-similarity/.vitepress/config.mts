import { defineConfig } from "vitepress";

const enNav = [
  { text: "Guide", link: "/project-guide.html" },
  { text: "CLI", link: "/cli.html" },
  { text: "API", link: "/api.html" },
  { text: "Rhythm Lab", link: "/rhythm-lab.html" }
];

const ruNav = [
  { text: "Руководство", link: "/ru/project-guide.html" },
  { text: "CLI", link: "/ru/cli.html" },
  { text: "API", link: "/ru/api.html" },
  { text: "Rhythm Lab", link: "/ru/rhythm-lab.html" }
];

const enSidebar = [
  {
    text: "Project",
    items: [
      { text: "Home", link: "/" },
      { text: "Guide", link: "/project-guide.html" },
      { text: "Overview", link: "/overview.html" },
      { text: "Architecture", link: "/architecture.html" },
      { text: "Database", link: "/database.html" },
      { text: "Development", link: "/development.html" }
    ]
  },
  {
    text: "Usage",
    items: [
      { text: "Analysis", link: "/analysis.html" },
      { text: "Search & Tags", link: "/search-and-tags.html" },
      { text: "CLI", link: "/cli.html" },
      { text: "Web API", link: "/api.html" }
    ]
  },
  {
    text: "Rhythm Lab",
    items: [{ text: "Rhythm Lab", link: "/rhythm-lab.html" }]
  },
  {
    text: "Maintenance",
    items: [
      { text: "Metadata Repair", link: "/scripts/repair-audio-metadata.html" },
      { text: "Dedup & Cleanup", link: "/scripts/audio-dedup.html" },
      { text: "DB Optimization", link: "/scripts/optimize-database.html" }
    ]
  }
];

const ruSidebar = [
  {
    text: "Проект",
    items: [
      { text: "Главная документации", link: "/ru/" },
      { text: "Путеводитель по проекту", link: "/ru/project-guide.html" },
      { text: "Обзор", link: "/ru/overview.html" },
      { text: "Архитектура и среда выполнения", link: "/ru/architecture.html" },
      { text: "База данных и сохраняемые данные", link: "/ru/database.html" },
      { text: "Разработка и проверка", link: "/ru/development.html" }
    ]
  },
  {
    text: "Использование приложения",
    items: [
      { text: "Семейства анализа", link: "/ru/analysis.html" },
      { text: "Поиск и запись тегов", link: "/ru/search-and-tags.html" },
      { text: "Справочник CLI", link: "/ru/cli.html" },
      { text: "Справочник Web API", link: "/ru/api.html" }
    ]
  },
  {
    text: "Rhythm Lab",
    items: [{ text: "Rhythm Lab", link: "/ru/rhythm-lab.html" }]
  },
  {
    text: "Служебные скрипты",
    items: [
      { text: "Восстановление аудиометаданных", link: "/ru/scripts/repair-audio-metadata.html" },
      { text: "Отчет о дублях аудио", link: "/ru/scripts/audio-dedup.html" },
      { text: "Оптимизация базы данных", link: "/ru/scripts/optimize-database.html" }
    ]
  }
];

export default defineConfig({
  title: "dj-track-similarity",
  description: "Local DJ music-library analysis and track similarity documentation.",
  lang: "en-US",
  base: "/docs/",
  outDir: "site",
  cleanUrls: false,
  appearance: false,
  lastUpdated: true,
  locales: {
    root: {
      label: "English",
      lang: "en-US",
      link: "/"
    },
    ru: {
      label: "Русский",
      lang: "ru-RU",
      link: "/ru/",
      title: "dj-track-similarity",
      description: "Документация локального инструмента анализа DJ-библиотеки и похожести треков.",
      themeConfig: {
        siteTitle: "Документация DJ Track Similarity",
        nav: ruNav,
        sidebar: ruSidebar,
        outline: {
          label: "На этой странице",
          level: [2, 3]
        },
        docFooter: {
          prev: "Назад",
          next: "Далее"
        },
        footer: {
          message: "Локальная документация, собранная из Markdown-файлов проекта.",
          copyright: "Документация публичной персональной утилиты."
        }
      }
    }
  },
  themeConfig: {
    siteTitle: "DJ Track Similarity Docs",
    nav: enNav,
    sidebar: enSidebar,
    search: {
      provider: "local",
      options: {
        locales: {
          ru: {
            translations: {
              button: {
                buttonText: "Поиск",
                buttonAriaLabel: "Поиск"
              },
              modal: {
                noResultsText: "Ничего не найдено",
                resetButtonTitle: "Очистить поиск",
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
    },
    outline: {
      level: [2, 3]
    },
    docFooter: {
      prev: "Previous",
      next: "Next"
    },
    footer: {
      message: "Local documentation generated from the project Markdown files.",
      copyright: "Public personal utility documentation."
    }
  }
});
