import { useState } from "react";
import { resolvePanelCollapsed, storePanelCollapsed, type CollapsiblePanel } from "./libraryView";

type WorkspaceView = "discover" | "analyze" | "library" | "search";

export function useWorkspacePanels() {
  const [setupCollapsed, setSetupCollapsed] = useState(() => resolvePanelCollapsed("setup"));
  const [libraryCollapsed, setLibraryCollapsed] = useState(() => resolvePanelCollapsed("library"));
  const [searchCollapsed, setSearchCollapsed] = useState(() => resolvePanelCollapsed("search"));
  // The export panel belongs to the SEARCH view, however that panel state was reached.
  const exportVisible = setupCollapsed && libraryCollapsed && !searchCollapsed;

  function togglePanel(panel: CollapsiblePanel) {
    const setters = { setup: setSetupCollapsed, library: setLibraryCollapsed, search: setSearchCollapsed };
    const collapsed = { setup: setupCollapsed, library: libraryCollapsed, search: searchCollapsed }[panel];
    storePanelCollapsed(panel, !collapsed);
    setters[panel](!collapsed);
  }

  function selectWorkspace(view: WorkspaceView) {
    setSetupCollapsed(view !== "discover" && view !== "analyze");
    setLibraryCollapsed(view !== "discover" && view !== "library");
    setSearchCollapsed(view !== "discover" && view !== "search");
  }

  return { setupCollapsed, libraryCollapsed, searchCollapsed, exportVisible, togglePanel, selectWorkspace };
}
