import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { clearStoredAccessToken, getStoredAccessToken, storeAccessToken } from "./session";

type AuthContextValue = {
  token: string | null;
  isAuthenticated: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredAccessToken());

  const signIn = useCallback((nextToken: string) => {
    storeAccessToken(nextToken);
    setToken(nextToken);
  }, []);

  const signOut = useCallback(() => {
    clearStoredAccessToken();
    setToken(null);
  }, []);

  useEffect(() => {
    const handleAuthExpired = () => signOut();
    window.addEventListener("z3r0:auth-expired", handleAuthExpired);
    return () => window.removeEventListener("z3r0:auth-expired", handleAuthExpired);
  }, [signOut]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      isAuthenticated: Boolean(token),
      signIn,
      signOut,
    }),
    [signIn, signOut, token],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
