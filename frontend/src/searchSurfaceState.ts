export type PrimarySearchTab = "sonara" | "mert" | "muq" | "mulan" | "clap" | "class" | "lab";
export type GenericSearchTab = Extract<PrimarySearchTab, "sonara" | "mert" | "muq" | "mulan" | "clap">;
export type TabNavigationKey = "ArrowLeft" | "ArrowRight" | "Home" | "End";

export const primarySearchTabs: readonly PrimarySearchTab[] = [
  "lab",
  "sonara",
  "mert",
  "muq",
  "mulan",
  "clap",
  "class"
];

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

export function genericSearchResultIsCurrent(
  activeTab: PrimarySearchTab,
  resultOrigin: GenericSearchTab | null,
  responseKey: string,
  currentKey: string
): boolean {
  return (
    resultOrigin !== null
    && activeTab === resultOrigin
    && Boolean(responseKey)
    && responseKey === currentKey
  );
}

function isTabNavigationKey(key: string): key is TabNavigationKey {
  return key === "ArrowLeft" || key === "ArrowRight" || key === "Home" || key === "End";
}
