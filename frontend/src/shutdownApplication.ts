type ShutdownApplicationOptions = {
  requestShutdown: () => Promise<unknown>;
  onAcknowledged: () => void;
  closeWindow: () => void;
};

export async function shutdownApplication({
  requestShutdown,
  onAcknowledged,
  closeWindow,
}: ShutdownApplicationOptions): Promise<void> {
  await requestShutdown();
  onAcknowledged();
  closeWindow();
}
