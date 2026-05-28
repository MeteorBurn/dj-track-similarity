export type ConfirmationRequest = {
  title: string;
  message: string;
  onConfirm: () => void | Promise<void>;
};
