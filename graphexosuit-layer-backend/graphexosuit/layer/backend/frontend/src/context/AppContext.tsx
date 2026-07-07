/**
 * graphexosuit.layer.backend.frontend.context.AppContext
 *
 * Responsibilities:
 *  - Provide React Context for global polling interval state
 *  - Offer updatePollingInterval() action
 *  - Limited scope: Only manages polling interval; all other state is local to screens/components
 */

import React, { createContext, useContext, useState, ReactNode } from 'react';

/** App context shape. */
interface AppContextType {
  pollingInterval: number;
  updatePollingInterval: (interval: number) => void;
}

/** Create context with undefined default (catch missing provider). */
const AppContext = createContext<AppContextType | undefined>(undefined);

interface AppProviderProps {
  children: ReactNode;
}

/**
 * App provider component.
 *
 * Why: Wrap app to provide polling interval state to all descendants.
 *
 * Args:
 *   children: React components to render within provider.
 */
export function AppProvider({ children }: AppProviderProps) {
  const [pollingInterval, setPollingInterval] = useState<number>(1000);

  const updatePollingInterval = (interval: number) => {
    // Constrain to valid range: 250-10000ms
    const clamped = Math.max(250, Math.min(10000, interval));
    setPollingInterval(clamped);
  };

  return (
    <AppContext.Provider value={{ pollingInterval, updatePollingInterval }}>
      {children}
    </AppContext.Provider>
  );
}

/**
 * Hook to access app context.
 *
 * Why: Retrieve polling interval and update function in components.
 *
 * Returns:
 *   App context value.
 *
 * Throws:
 *   If called outside AppProvider.
 */
export function useAppContext(): AppContextType {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within AppProvider');
  }
  return context;
}
