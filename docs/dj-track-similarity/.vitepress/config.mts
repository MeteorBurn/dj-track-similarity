import { defineConfig } from "vitepress";

export default defineConfig({
  title: "dj-track-similarity",
  description: "Local DJ music-library analysis and track similarity documentation.",
  lang: "en-US",
  base: "/docs/",
  outDir: "site",
  cleanUrls: false,
  appearance: false,
  lastUpdated: true,
  themeConfig: {
    siteTitle: "DJ Track Similarity Docs",
    nav: [
      { text: "Guide", link: "/project-guide.html" },
      { text: "CLI", link: "/cli.html" },
      { text: "API", link: "/api.html" },
      { text: "Rhythm Lab", link: "/rhythm-lab.html" }
    ],
    sidebar: [
      {
        text: "Project",
        items: [
          { text: "Documentation Home", link: "/" },
          { text: "Project Guide", link: "/project-guide.html" },
          { text: "Overview", link: "/overview.html" },
          { text: "Architecture and Runtime", link: "/architecture.html" },
          { text: "Database and Stored Data", link: "/database.html" },
          { text: "Development and Verification", link: "/development.html" }
        ]
      },
      {
        text: "Using the App",
        items: [
          { text: "Analysis Families", link: "/analysis.html" },
          { text: "Search and Tag Writing", link: "/search-and-tags.html" },
          { text: "CLI Reference", link: "/cli.html" },
          { text: "Web API Reference", link: "/api.html" }
        ]
      },
      {
        text: "Rhythm Lab",
        items: [{ text: "Rhythm Lab", link: "/rhythm-lab.html" }]
      },
      {
        text: "Maintenance Scripts",
        items: [
          { text: "Audio Metadata Repair", link: "/scripts/repair-audio-metadata.html" },
          { text: "Audio Dedup Report", link: "/scripts/audio-dedup.html" },
          { text: "Database Optimization", link: "/scripts/optimize-database.html" }
        ]
      }
    ],
    search: {
      provider: "local"
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
