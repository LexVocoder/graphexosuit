/**
 * graphexosuit.layer.backend.frontend.main
 *
 * Responsibilities:
 *  - Entry point for React application
 *  - Mount App component to DOM root
 *  - Import global styles
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from '@/App';
import '@/styles/globals.css';

// Mount React app to root element
const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element not found in HTML');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
