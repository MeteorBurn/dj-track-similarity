import { defineConfig } from "vitepress";

const enNav = [
  { text: "Start", link: "/getting-started/quickstart.html" },
  { text: "User Guide", link: "/user-guide/" },
  { text: "Workflows", link: "/workflows/" },
  { text: "Tools", link: "/tools-and-scripts/" },
  { text: "Reference", link: "/reference/" },
  { text: "Help", link: "/help/" }
];

const ruNav = [
  { text: "Старт", link: "/ru/getting-started/quickstart.html" },
  { text: "UI-гайд", link: "/ru/user-guide/" },
  { text: "Workflows", link: "/ru/workflows/" },
  { text: "Tools", link: "/ru/tools-and-scripts/" },
  { text: "Reference", link: "/ru/reference/" },
  { text: "Help", link: "/ru/help/" }
];

const enSidebar = [
  {
    text: "Start",
    items: [
      { text: "Home", link: "/" },
      { text: "Getting Started", link: "/getting-started/" },
      { text: "Quickstart", link: "/getting-started/quickstart.html" },
      { text: "Install", link: "/getting-started/install.html" },
      { text: "First Library", link: "/getting-started/first-library.html" },
      { text: "First Analysis", link: "/getting-started/first-analysis.html" }
    ]
  },
  {
    text: "User Guide",
    items: [
      { text: "Guide Index", link: "/user-guide/" },
      { text: "Browse Library", link: "/user-guide/browse-library.html" },
      { text: "Analyze Library", link: "/user-guide/analyze-library.html" },
      { text: "Search With Seeds", link: "/user-guide/search-with-seeds.html" },
      { text: "Smart Set Builder", link: "/user-guide/smart-set-builder.html" },
      { text: "Text Search", link: "/user-guide/text-search.html" },
      { text: "CLASS Tab", link: "/user-guide/class-tab.html" },
      { text: "Export Playlists", link: "/user-guide/export-playlists.html" },
      { text: "Tags and Audio Writes", link: "/user-guide/tags-and-audio-writes.html" }
    ]
  },
  {
    text: "Workflows",
    items: [
      { text: "Workflow Index", link: "/workflows/" },
      { text: "Prepare a Set", link: "/workflows/prepare-a-set.html" },
      { text: "Find Compatible Tracks", link: "/workflows/find-compatible-tracks.html" },
      { text: "Build Crates", link: "/workflows/build-crates.html" },
      { text: "Train a Personal Classifier", link: "/workflows/train-personal-classifier.html" },
      { text: "Maintain the Library", link: "/workflows/maintain-library.html" }
    ]
  },
  {
    text: "Concepts",
    items: [
      { text: "Concept Index", link: "/concepts/" },
      { text: "Local-first Safety", link: "/concepts/local-first-safety.html" },
      { text: "Features, Embeddings, Tags", link: "/concepts/features-embeddings-tags.html" },
      { text: "Similarity Scores", link: "/concepts/similarity-scores.html" },
      { text: "SET Routing", link: "/concepts/smart-set-builder-routing.html" },
      { text: "Classifiers and Rhythm Lab", link: "/concepts/classifiers-and-rhythm-lab.html" }
    ]
  },
  {
    text: "Tools",
    items: [
      { text: "Tools Index", link: "/tools-and-scripts/" },
      { text: "Rhythm Lab", link: "/tools-and-scripts/rhythm-lab.html" },
      { text: "Audio Dedup", link: "/tools-and-scripts/audio-dedup.html" },
      { text: "Audio Repair", link: "/tools-and-scripts/repair-audio-metadata.html" },
      { text: "Optimize Database", link: "/tools-and-scripts/optimize-database.html" }
    ]
  },
  {
    text: "Reference",
    items: [
      { text: "Reference Index", link: "/reference/" },
      { text: "CLI", link: "/reference/cli.html" },
      { text: "API", link: "/reference/api.html" },
      { text: "Database", link: "/reference/database.html" },
      { text: "Configuration", link: "/reference/configuration.html" },
      { text: "Analysis Families", link: "/reference/analysis-families.html" },
      { text: "UI Controls", link: "/reference/ui-controls.html" }
    ]
  },
  {
    text: "Developer",
    items: [
      { text: "Developer Index", link: "/developer/" },
      { text: "Architecture", link: "/developer/architecture.html" },
      { text: "Development", link: "/developer/development.html" },
      { text: "Testing and Verification", link: "/developer/testing-and-verification.html" },
      { text: "Release Checklist", link: "/developer/release-checklist.html" }
    ]
  },
  {
    text: "Help",
    items: [
      { text: "Help Index", link: "/help/" },
      { text: "Troubleshooting", link: "/help/troubleshooting.html" },
      { text: "FAQ", link: "/help/faq.html" },
      { text: "Known Limits", link: "/help/known-limits.html" }
    ]
  }
];

const ruSidebar = [
  {
    text: "Старт",
    items: [
      { text: "Главная", link: "/ru/" },
      { text: "Getting Started", link: "/ru/getting-started/" },
      { text: "Quickstart", link: "/ru/getting-started/quickstart.html" },
      { text: "Install", link: "/ru/getting-started/install.html" },
      { text: "First Library", link: "/ru/getting-started/first-library.html" },
      { text: "First Analysis", link: "/ru/getting-started/first-analysis.html" }
    ]
  },
  {
    text: "UI-гайд",
    items: [
      { text: "Guide Index", link: "/ru/user-guide/" },
      { text: "Browse Library", link: "/ru/user-guide/browse-library.html" },
      { text: "Analyze Library", link: "/ru/user-guide/analyze-library.html" },
      { text: "Search With Seeds", link: "/ru/user-guide/search-with-seeds.html" },
      { text: "Smart Set Builder", link: "/ru/user-guide/smart-set-builder.html" },
      { text: "Text Search", link: "/ru/user-guide/text-search.html" },
      { text: "CLASS Tab", link: "/ru/user-guide/class-tab.html" },
      { text: "Export Playlists", link: "/ru/user-guide/export-playlists.html" },
      { text: "Tags and Audio Writes", link: "/ru/user-guide/tags-and-audio-writes.html" }
    ]
  },
  {
    text: "Workflows",
    items: [
      { text: "Workflow Index", link: "/ru/workflows/" },
      { text: "Prepare a Set", link: "/ru/workflows/prepare-a-set.html" },
      { text: "Find Compatible Tracks", link: "/ru/workflows/find-compatible-tracks.html" },
      { text: "Build Crates", link: "/ru/workflows/build-crates.html" },
      { text: "Train a Personal Classifier", link: "/ru/workflows/train-personal-classifier.html" },
      { text: "Maintain the Library", link: "/ru/workflows/maintain-library.html" }
    ]
  },
  {
    text: "Concepts",
    items: [
      { text: "Concept Index", link: "/ru/concepts/" },
      { text: "Local-first Safety", link: "/ru/concepts/local-first-safety.html" },
      { text: "Features, Embeddings, Tags", link: "/ru/concepts/features-embeddings-tags.html" },
      { text: "Similarity Scores", link: "/ru/concepts/similarity-scores.html" },
      { text: "SET Routing", link: "/ru/concepts/smart-set-builder-routing.html" },
      { text: "Classifiers and Rhythm Lab", link: "/ru/concepts/classifiers-and-rhythm-lab.html" }
    ]
  },
  {
    text: "Tools",
    items: [
      { text: "Tools Index", link: "/ru/tools-and-scripts/" },
      { text: "Rhythm Lab", link: "/ru/tools-and-scripts/rhythm-lab.html" },
      { text: "Audio Dedup", link: "/ru/tools-and-scripts/audio-dedup.html" },
      { text: "Audio Repair", link: "/ru/tools-and-scripts/repair-audio-metadata.html" },
      { text: "Optimize Database", link: "/ru/tools-and-scripts/optimize-database.html" }
    ]
  },
  {
    text: "Reference",
    items: [
      { text: "Reference Index", link: "/ru/reference/" },
      { text: "CLI", link: "/ru/reference/cli.html" },
      { text: "API", link: "/ru/reference/api.html" },
      { text: "Database", link: "/ru/reference/database.html" },
      { text: "Configuration", link: "/ru/reference/configuration.html" },
      { text: "Analysis Families", link: "/ru/reference/analysis-families.html" },
      { text: "UI Controls", link: "/ru/reference/ui-controls.html" }
    ]
  },
  {
    text: "Developer",
    items: [
      { text: "Developer Index", link: "/ru/developer/" },
      { text: "Architecture", link: "/ru/developer/architecture.html" },
      { text: "Development", link: "/ru/developer/development.html" },
      { text: "Testing and Verification", link: "/ru/developer/testing-and-verification.html" },
      { text: "Release Checklist", link: "/ru/developer/release-checklist.html" }
    ]
  },
  {
    text: "Help",
    items: [
      { text: "Help Index", link: "/ru/help/" },
      { text: "Troubleshooting", link: "/ru/help/troubleshooting.html" },
      { text: "FAQ", link: "/ru/help/faq.html" },
      { text: "Known Limits", link: "/ru/help/known-limits.html" }
    ]
  }
];

export default defineConfig({
  title: "dj-track-similarity",
  description: "Local DJ music-library analysis and track similarity documentation.",
  lang: "en-US",
  base: "/docs/",
  head: [["link", { rel: "icon", type: "image/svg+xml", href: "/docs/favicon.svg" }]],
  outDir: "site",
  cleanUrls: false,
  appearance: true,
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
        siteTitle: "DJ Track Similarity Docs",
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
    logo: { light: "/logo-light.svg", dark: "/logo-dark.svg", alt: "DJ Track Similarity" },
    nav: enNav,
    sidebar: enSidebar,
    socialLinks: [
      { icon: "github", link: "https://github.com/MeteorBurn/dj-track-similarity" }
    ],
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
      level: [2, 3],
      label: "On this page"
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
