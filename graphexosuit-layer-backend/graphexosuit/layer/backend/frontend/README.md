# GraphExosuit Frontend

A React + TypeScript frontend for the GraphExosuit REST API. Provides real-time execution monitoring, interrupt handling, and result display.

## Features

- **Pre-run screen**: JSON editor with validation for setting initial graph state
- **Execution monitoring**: Real-time output streaming with scrollable, resizable display
- **Interrupt handling**: Select interrupt options and edit resume payloads before continuing
- **Error handling**: Display errors with retry capability
- **Polling control**: Adjustable polling interval (250-10000ms, default 1000ms)
- **Accessibility**: Full keyboard navigation, ARIA labels, WCAG AA color contrast

## Prerequisites

- Node.js 16+
- npm

## Installation

```bash
cd graphexosuit/layer/backend/frontend
npm install
```

## Development

Start the development server with hot module reloading:

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173` by default.

**Note**: The dev server is configured to proxy API requests to `http://localhost:8000`. To use a different backend URL, set the `VITE_API_BASE_URL` environment variable:

```bash
VITE_API_BASE_URL=http://your-backend:8000 npm run dev
```

## Build

Create a production build:

```bash
npm run build
```

Output is generated in `dist/` directory with hashed assets for cache-busting.

## Usage

### Mounting in FastAPI

The consuming server can serve the built frontend from `dist/` at the root path. Example Python helper (optional):

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Mount static files
frontend_dist = Path(__file__).parent / "frontend" / "dist"
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
```

### Deployment

1. Build the frontend: `npm run build`
2. Serve `dist/` as static files from your web server
3. Configure `VITE_API_BASE_URL` to point to your GraphExosuit backend

## Architecture

### Project Structure

```
src/
├── api/
│   └── client.ts           # HTTP API client
├── components/
│   ├── InterruptPrompt.tsx     # Interrupt option selection
│   ├── JSONEditorModal.tsx     # Monaco JSON editor
│   ├── OutputTextBox.tsx       # Scrollable output display
│   └── StatusBadge.tsx         # Status indicator
├── context/
│   └── AppContext.tsx      # Global polling interval state
├── screens/
│   ├── ExecutionProgressScreen.tsx  # Execution monitoring & control
│   └── PreRunScreen.tsx             # Initial state input
├── styles/
│   └── globals.css         # Global Tailwind + custom CSS
├── types/
│   └── api.ts              # TypeScript API types
├── App.tsx                 # Root router component
└── main.tsx                # Entry point
```

### State Management

- **App Context**: Manages polling interval (250-10000ms, default 1000ms)
- **Local State**: Each screen/component manages its own state (thread_id, execution data, form inputs)

### Key Components

#### PreRunScreen
- Monaco JSON editor with prettified `{"initial_value":{"key":"value"}}` template
- Real-time JSON validation
- Run button (disabled if JSON invalid or request pending)

#### ExecutionProgressScreen
- Real-time output display (95% width, 25 rows default, drag-resizable)
- Smart scrolling: auto-scroll if at bottom, preserve position otherwise
- Polling interval slider (250-10000ms)
- Status-based UI:
  - **Running**: Display output and polling status
  - **Paused**: Show interrupt options, allow JSON editing of resume payload
  - **Completed**: Display final result (pretty-printed JSON)
  - **Error**: Show error message with retry option

#### OutputTextBox
- Monospace, word-wrapped output display
- Draggable resize handle at bottom (desktop only)
- Auto-scroll to bottom if already at bottom
- Height persisted to localStorage
- Scroll position indicator when new output arrives

## Accessibility

- **ARIA labels** on all interactive elements
- **Keyboard navigation**: Tab/Shift+Tab through controls, Enter to activate buttons
- **Focus management**: Visible focus ring on all interactive elements
- **Semantic HTML**: Native elements used where possible
- **Color contrast**: WCAG AA minimum (4.5:1 for text, 3:1 for UI)
- **Screen reader support**: Live regions for status updates, error messages

## Environment Variables

Create `.env.local` to override defaults:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Troubleshooting

### Build errors

Ensure all dependencies are installed:

```bash
npm install
```

Clear build cache if needed:

```bash
rm -rf dist node_modules package-lock.json
npm install
npm run build
```

### API connection issues

Verify the backend is running and accessible at the configured `VITE_API_BASE_URL`.

In development, the dev server proxies `/run`, `/thread`, etc. to the backend. Update `vite.config.ts` if needed.

## Dependencies

- **react** 18: UI framework
- **react-dom** 18: React DOM rendering
- **@monaco-editor/react**: JSON editor component
- **axios**: HTTP client
- **typescript**: Type safety
- **tailwindcss**: Utility-first styling
- **vite**: Build tool

## License

See root project LICENSE.
