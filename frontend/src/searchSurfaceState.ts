export type PrimarySearchTab = "sonara" | "similarity" | "clap" | "class" | "lab";
export type SeedEmbeddingFamily = "mert" | "muq" | "mulan";
export type GenericSearchTab = Extract<PrimarySearchTab, "sonara" | "clap"> | SeedEmbeddingFamily;
export type TabNavigationKey = "ArrowLeft" | "ArrowRight" | "Home" | "End";

export const primarySearchTabs: readonly PrimarySearchTab[] = [
  "lab",
  "sonara",
  "similarity",
  "clap",
  "class"
];

export const seedEmbeddingFamilies: readonly SeedEmbeddingFamily[] = ["mert", "muq", "mulan"];

export const seedEmbeddingFamilyPresentation: Record<SeedEmbeddingFamily, { label: string; title: string }> = {
  mert: { label: "MERT", title: "MERT seed embedding search" },
  muq: { label: "MuQ", title: "MuQ seed embedding search" },
  mulan: { label: "MuQ-MuLan", title: "MuQ-MuLan seed embedding search" }
};

export type RequestTokenGuard = {
  begin: () => number;
  invalidate: () => void;
  isCurrent: (token: number) => boolean;
};

export function tabAfterKey<T extends string>(
  tabs: readonly T[],
  active: T,
  key: string
): T | null {
  if (!isTabNavigationKey(key) || tabs.length === 0) return null;
  if (key === "Home") return tabs[0];
  if (key === "End") return tabs[tabs.length - 1];
  const currentIndex = Math.max(0, tabs.indexOf(active));
  const delta = key === "ArrowRight" ? 1 : -1;
  return tabs[(currentIndex + delta + tabs.length) % tabs.length];
}

export function createRequestTokenGuard(): RequestTokenGuard {
  let currentToken = 0;
  return {
    begin() {
      currentToken += 1;
      return currentToken;
    },
    invalidate() {
      currentToken += 1;
    },
    isCurrent(token) {
      return currentToken === token;
    }
  };
}

export function isSeedEmbeddingFamily(value: string): value is SeedEmbeddingFamily {
  return seedEmbeddingFamilies.includes(value as SeedEmbeddingFamily);
}

export function searchTabForResultOrigin(origin: GenericSearchTab): PrimarySearchTab {
  return isSeedEmbeddingFamily(origin) ? "similarity" : origin;
}

export function genericSearchResultIsCurrent(
  activeTab: PrimarySearchTab,
  resultOrigin: GenericSearchTab | null,
  responseKey: string,
  currentKey: string
): boolean {
  return (
    resultOrigin !== null
    && activeTab === searchTabForResultOrigin(resultOrigin)
    && Boolean(responseKey)
    && responseKey === currentKey
  );
}

function isTabNavigationKey(key: string): key is TabNavigationKey {
  return key === "ArrowLeft" || key === "ArrowRight" || key === "Home" || key === "End";
}
