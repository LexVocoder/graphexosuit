/**
 * graphexosuit.layer.backend.frontend.App
 *
 * Responsibilities:
 *  - Root app component with screen router
 *  - Provide AppContext to all descendants
 *  - Manage navigation between PreRunScreen and ExecutionProgressScreen
 *  - Maintain thread_id state across screens
 */

import React, { useState } from 'react';
import { AppProvider } from '@/context/AppContext';
import PreRunScreen from '@/screens/PreRunScreen';
import ExecutionProgressScreen from '@/screens/ExecutionProgressScreen';

type CurrentScreen = 'pre-run' | 'execution-progress';

/**
 * App component: Root of application with screen router.
 *
 * Why: Manages top-level state (current screen, thread_id) and navigates between screens.
 */
function App() {
  const [currentScreen, setCurrentScreen] = useState<CurrentScreen>('pre-run');
  const [threadId, setThreadId] = useState<string | null>(null);

  /**
   * Handle starting a run: transition to execution-progress screen.
   */
  const handleStartRun = (newThreadId: string) => {
    setThreadId(newThreadId);
    setCurrentScreen('execution-progress');
  };

  /**
   * Handle returning to pre-run screen (Start Over button).
   */
  const handleResetToPreRun = () => {
    setThreadId(null);
    setCurrentScreen('pre-run');
  };

  return (
    <AppProvider>
      <div className="min-h-screen bg-white text-gray-900">
        <header className="border-b border-gray-200 bg-gray-50">
          <div className="container-centered safe-container">
            <h1 className="text-3xl font-bold text-gray-900">GraphExosuit</h1>
          </div>
        </header>

        <main className="container-centered safe-container">
          {currentScreen === 'pre-run' && (
            <PreRunScreen onStartRun={handleStartRun} />
          )}
          {currentScreen === 'execution-progress' && threadId && (
            <ExecutionProgressScreen
              threadId={threadId}
              onResetToPreRun={handleResetToPreRun}
            />
          )}
        </main>
      </div>
    </AppProvider>
  );
}

export default App;
