import { defineConfig } from "vitepress";

type SidebarSection = { text: string; items: { text: string; link: string }[] };

const englishNav = [
  { text: "Home", link: "/" },
  { text: "Guide", link: "/project-guide.html" },
  { text: "Getting Started", link: "/getting-started/quickstart.html" },
  { text: "User Guide", link: "/user-guide/" },
  { text: "Reference", link: "/reference/" }
];

const englishSidebar: SidebarSection[] = [
  { text: "Start", items: [{ text: "Home", link: "/" }, { text: "Project guide", link: "/project-guide.html" }] },
  { text: "Getting started", items: [{ text: "Overview", link: "/getting-started/" }, { text: "Quickstart", link: "/getting-started/quickstart.html" }, { text: "Install", link: "/getting-started/install.html" }, { text: "First library", link: "/getting-started/first-library.html" }, { text: "First analysis", link: "/getting-started/first-analysis.html" }] },
  { text: "User guide", items: [{ text: "Overview", link: "/user-guide/" }, { text: "Browse library", link: "/user-guide/browse-library.html" }, { text: "Analyze library", link: "/user-guide/analyze-library.html" }, { text: "Search with seeds", link: "/user-guide/search-with-seeds.html" }, { text: "Smart Set Builder", link: "/user-guide/smart-set-builder.html" }, { text: "Text search", link: "/user-guide/text-search.html" }, { text: "CLASS tab", link: "/user-guide/class-tab.html" }, { text: "Export playlists", link: "/user-guide/export-playlists.html" }, { text: "Tags and audio writes", link: "/user-guide/tags-and-audio-writes.html" }] },
  { text: "Workflows", items: [{ text: "Overview", link: "/workflows/" }, { text: "Prepare a set", link: "/workflows/prepare-a-set.html" }, { text: "Find compatible tracks", link: "/workflows/find-compatible-tracks.html" }, { text: "Build crates", link: "/workflows/build-crates.html" }, { text: "Train classifier", link: "/workflows/train-personal-classifier.html" }, { text: "Maintain library", link: "/workflows/maintain-library.html" }] },
  { text: "Concepts", items: [{ text: "Overview", link: "/concepts/" }, { text: "Local-first safety", link: "/concepts/local-first-safety.html" }, { text: "Features, embeddings, tags", link: "/concepts/features-embeddings-tags.html" }, { text: "Similarity scores", link: "/concepts/similarity-scores.html" }, { text: "SET routing", link: "/concepts/smart-set-builder-routing.html" }, { text: "Classifiers and Rhythm Lab", link: "/concepts/classifiers-and-rhythm-lab.html" }] },
  { text: "Tools and scripts", items: [{ text: "Overview", link: "/tools-and-scripts/" }, { text: "Rhythm Lab", link: "/tools-and-scripts/rhythm-lab.html" }, { text: "Audio Dedup", link: "/tools-and-scripts/audio-dedup.html" }, { text: "Audio Doctor", link: "/tools-and-scripts/audio-doctor.html" }, { text: "Persistent ANN indexes", link: "/tools-and-scripts/persistent-ann-indexes.html" }, { text: "Optimize database", link: "/tools-and-scripts/optimize-database.html" }] },
  { text: "Reference", items: [{ text: "Overview", link: "/reference/" }, { text: "CLI", link: "/reference/cli.html" }, { text: "API", link: "/reference/api.html" }, { text: "Database", link: "/reference/database.html" }, { text: "Configuration", link: "/reference/configuration.html" }, { text: "Analysis families", link: "/reference/analysis-families.html" }, { text: "UI controls", link: "/reference/ui-controls.html" }] },
  { text: "Developer", items: [{ text: "Overview", link: "/developer/" }, { text: "Architecture", link: "/developer/architecture.html" }, { text: "Development", link: "/developer/development.html" }, { text: "Testing", link: "/developer/testing-and-verification.html" }, { text: "Release checklist", link: "/developer/release-checklist.html" }] },
  { text: "Help", items: [{ text: "Overview", link: "/help/" }, { text: "Troubleshooting", link: "/help/troubleshooting.html" }, { text: "FAQ", link: "/help/faq.html" }, { text: "Known limits", link: "/help/known-limits.html" }] }
];

const commonTheme = {
  siteTitle: "DJ Track Similarity Docs",
  logo: { light: "/logo-light.svg", dark: "/logo-dark.svg", alt: "DJ Track Similarity" },
  socialLinks: [{ icon: "github", link: "https://github.com/MeteorBurn/dj-track-similarity" }],
  search: { provider: "local" },
  outline: { level: [2, 3], label: "On this page" },
  docFooter: { prev: "Previous", next: "Next" },
  footer: { message: "Local-first DJ library analysis documentation.", copyright: "Public personal utility documentation." }
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
  themeConfig: { ...commonTheme, nav: englishNav, sidebar: englishSidebar }
});
