const CONNECT_TIMEOUT_MS = 15 * 1000;

export function waitOpen(socket: WebSocket): Promise<void> {
  if (socket.readyState === WebSocket.OPEN) return Promise.resolve();
  if (socket.readyState !== WebSocket.CONNECTING) {
    return Promise.reject(new Error("websocket connection closed"));
  }
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      window.clearTimeout(timer);
      socket.removeEventListener("open", onOpen);
      socket.removeEventListener("error", onError);
      socket.removeEventListener("close", onClose);
    };
    const onOpen = () => { cleanup(); resolve(); };
    const onError = () => { cleanup(); reject(new Error("websocket connection failed")); };
    const onClose = () => { cleanup(); reject(new Error("websocket connection closed")); };
    const timer = window.setTimeout(() => { cleanup(); reject(new Error("websocket connection timed out")); }, CONNECT_TIMEOUT_MS);
    socket.addEventListener("open", onOpen);
    socket.addEventListener("error", onError);
    socket.addEventListener("close", onClose);
  });
}
