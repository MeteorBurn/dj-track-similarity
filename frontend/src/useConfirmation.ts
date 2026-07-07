import { useState } from "react";
import type { ConfirmationRequest } from "./confirmation";

type ConfirmationState = {
  readonly confirmation: ConfirmationRequest | null;
  readonly requestConfirmation: (request: ConfirmationRequest) => void;
  readonly confirmPendingAction: () => void;
  readonly cancelConfirmation: () => void;
};

export function useConfirmation(): ConfirmationState {
  const [confirmation, setConfirmation] = useState<ConfirmationRequest | null>(null);

  function requestConfirmation(request: ConfirmationRequest) {
    setConfirmation(request);
  }

  function confirmPendingAction() {
    const pending = confirmation;
    if (!pending) return;
    setConfirmation(null);
    void pending.onConfirm();
  }

  function cancelConfirmation() {
    setConfirmation(null);
  }

  return { confirmation, requestConfirmation, confirmPendingAction, cancelConfirmation };
}
