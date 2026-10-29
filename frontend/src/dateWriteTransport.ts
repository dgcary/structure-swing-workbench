/** Keep privileged Bearer tokens off remote plaintext pages. */
export function canSendDateWriteToken(protocol: string, hostname: string): boolean {
  if (protocol === "https:") return true;
  if (protocol !== "http:") return false;
  const host = hostname.toLowerCase();
  return host === "localhost" || host === "127.0.0.1" || host === "[::1]" || host === "::1";
}
