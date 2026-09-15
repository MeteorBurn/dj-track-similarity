export type PrimarySearchTab = "similarity" | "text" | "class" | "lab";
export type SeedEmbeddingFamily = "maest" | "mert" | "mert_v2" | "muq" | "mulan" | "clap";
export type SeedSearchModel = "sonara" | SeedEmbeddingFamily;
export type GenericSearchTab = "text" | SeedSearchModel;
export type TabNavigationKey = "ArrowLeft" | "ArrowRight" | "Home" | "End";

export const primarySearchTabs: readonly PrimarySearchTab[] = [
  "lab",
  "similarity",
  "text",
  "class"
];

export const seedEmbeddingFamilies: readonly SeedEmbeddingFamily[] = ["maest", "mert", "mert_v2", "muq", "mulan", "clap"];
export const seedSearchModels: readonly SeedSearchModel[] = ["sonara", ...seedEmbeddingFamilies];

export const seedSearchModelPresentation: Record<SeedSearchModel, { label: string; title: string; description: string }> = {
  sonara: {
    label: "SONARA",
    title: "SONARA similarity search",
    description: "Сравнивает тембр, ритм, динамику, гармонию и темп по измеренным признакам. Их вклад можно настроить."
  },
  maest: {
    label: "MAEST",
    title: "MAEST seed embedding search",
    description: "Сравнивает звучание через признаки модели, обученной распознавать жанры и стили музыки."
  },
  mert: {
    label: "MERT",
    title: "MERT seed embedding search",
    description: "Сравнивает общее звучание по музыкальным признакам, которые нейросеть извлекает из аудио."
  },
  mert_v2: {
    label: "MERT-v2",
    title: "MERT-v2 seed embedding search",
    description: "Сравнивает треки по сохранённым признакам MERT-v2. Несколько seed задают общее направление поиска."
  },
  muq: {
    label: "MuQ",
    title: "MuQ seed embedding search",
    description: "Сравнивает звучание по выученным акустическим признакам и их контексту в музыкальных фрагментах."
  },
  mulan: {
    label: "MuQ-MuLan",
    title: "MuQ-MuLan seed embedding search",
    description: "Сравнивает звучание через модель, связывающую музыку со словесными описаниями."
  },
  clap: {
    label: "CLAP",
    title: "CLAP seed embedding search",
    description: "Сравнивает звучание через модель, связывающую аудио со словесными описаниями."
  }
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
  return origin === "text" ? "text" : "similarity";
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
