# LinkedIn Session Keeper

A standalone service that manages LinkedIn sessions using Playwright with VNC/noVNC support for manual login.

## Features

- **Persistent Browser Sessions**: Uses Playwright's persistent context to save and reuse LinkedIn sessions
- **VNC Access**: Provides VNC (port 5901) and noVNC web interface (port 6080) for manual login
- **Automatic Keep-Alive**: Refreshes LinkedIn feed every 20 minutes to keep session active
- **First-Run Detection**: Automatically opens headful browser on first run for manual login
- **Session Management**: Clear and restart sessions via API

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  LinkedIn Session Keeper Container                      │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Xvfb       │  │  Playwright  │  │  Node.js API │ │
│  │  (Display)   │  │  (Chromium)  │  │  (Port 3001) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│         │                 │                  │          │
│  ┌──────────────┐  ┌──────────────┐         │          │
│  │   x11vnc     │  │   noVNC      │         │          │
│  │  (Port 5901) │  │  (Port 6080) │         │          │
│  └──────────────┘  └──────────────┘         │          │
│                                              │          │
│  Volume: /app/linkedin-profile (persistent) │          │
└─────────────────────────────────────────────────────────┘
```

## API Endpoints

### POST /start
Start the LinkedIn session automation.

**Response:**
```json
{
  "message": "Session active. Keep-alive enabled."
}
```

### POST /clear
Clear the saved session and profile data.

**Response:**
```json
{
  "message": "Saved session cleared. Next run will be headful for login."
}
```

### GET /
Serves the web UI for managing the session keeper.

## Environment Variables

- `PORT`: API server port (default: 3001)
- `FRONTEND_ORIGIN`: CORS origin (default: *)
- `HEADLESS`: Force headless mode (default: auto - headful on first run, headless after)

## Usage

### Via Docker Compose

The service is integrated into the main docker-compose.yml:

```bash
# Start all services including linkedin-keeper
docker compose up -d

# View logs
docker compose logs -f linkedin-keeper

# Access the web UI
open http://localhost:3001

# Access noVNC
open http://localhost:6080
```

### First Run (Manual Login)

1. Click "Start Automation" in the web UI
2. Click "Open Browser Console (noVNC)" to view the browser
3. Log in to LinkedIn manually via the VNC interface
4. Navigate to your LinkedIn feed
5. The session will be automatically saved

### Subsequent Runs

1. Click "Start Automation"
2. The saved session will be loaded automatically
3. LinkedIn feed will open in headless mode
4. Keep-alive refreshes will maintain the session

## Integration with Main Application

The LinkedIn session keeper replaces the previous VNC-based account addition method. The saved browser profile can be used by the main application's campaign automation:

1. **Session Storage**: Profile saved in `/app/linkedin-profile` volume
2. **Cookie Extraction**: Cookies can be extracted from the persistent context
3. **Campaign Usage**: The saved session is reused for all LinkedIn automation tasks

## Troubleshooting

### Session not saving
- Ensure you navigate to the LinkedIn feed after logging in
- Check that the `/app/linkedin-profile` volume has write permissions

### VNC not accessible
- Verify ports 5901 and 6080 are exposed and not blocked by firewall
- Check that Xvfb and x11vnc are running: `docker exec linkedin-keeper ps aux | grep vnc`

### Browser crashes
- Increase shared memory: `shm_size: '2gb'` in docker-compose.yml
- Check Xvfb logs: `docker exec linkedin-keeper cat /tmp/xvfb.log`

## Development

```bash
cd linkedin-keeper

# Install dependencies
npm install

# Run locally (requires X11 or Xvfb)
npm start

# Build Docker image
docker build -t linkedin-keeper .

# Run container
docker run -p 3001:3001 -p 5901:5901 -p 6080:6080 \
  -v linkedin-profile:/app/linkedin-profile \
  --shm-size=2gb \
  linkedin-keeper
```

## Security Notes

- VNC is not password-protected by default (uses `-nopw` flag)
- For production, add VNC password or restrict access via firewall
- The noVNC web interface should be behind authentication in production
- LinkedIn credentials are never stored - only browser cookies/session data
