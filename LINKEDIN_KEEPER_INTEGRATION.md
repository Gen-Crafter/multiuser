# LinkedIn Session Keeper Integration

## Overview

The LinkedIn connection logic has been replaced with a new Playwright-based session keeper that uses VNC for manual login and persistent browser contexts. This provides a more robust and maintainable approach to LinkedIn account management.

## What Changed

### 1. New LinkedIn Session Keeper Service

**Location**: `linkedin-keeper/`

A standalone Node.js service that:
- Manages LinkedIn sessions using Playwright persistent contexts
- Provides VNC (port 5901) and noVNC web interface (port 6080) for manual login
- Automatically keeps sessions alive with periodic refreshes
- Detects first run and opens headful browser for manual login
- Saves browser profile for reuse in subsequent runs

**Key Files**:
- `index.js` - Main session keeper logic
- `Dockerfile` - Container with Playwright, VNC, noVNC
- `entrypoint.sh` - Starts Xvfb, x11vnc, websockify, and Node.js
- `public/index.html` - Web UI for session management

### 2. Docker Compose Changes

**File**: `docker-compose.yml`

- **Removed**: `vnc-browser` service (old dorowu image)
- **Added**: `linkedin-keeper` service with:
  - Port 3001: Session keeper API
  - Port 5901: VNC server
  - Port 6080: noVNC web interface
  - Volume: `linkedin_profile` for persistent browser data
  - Shared memory: 2GB for Chromium

### 3. Frontend Integration

**New Page**: `frontend/src/app/dashboard/linkedin-keeper/page.tsx`

A dedicated page for managing LinkedIn sessions with:
- Start Automation button
- Open Browser Console (noVNC) button
- Clear Saved Session button
- Real-time status display

### 4. Existing Code Preserved

The following existing code is **preserved** for now:
- `backend/app/automation/vnc_session_manager.py` - Can be deprecated later
- `backend/app/api/vnc_sessions.py` - Can be deprecated later
- `frontend/src/app/dashboard/accounts/page.tsx` - Existing accounts page

## Deployment Instructions

### Step 1: Build and Start Services

On your VM:

```bash
cd ~/multiuser

# Pull latest code (ensure docker-compose.yml and linkedin-keeper/ are synced)
git pull  # or manually sync files

# Build the new linkedin-keeper service
docker compose build linkedin-keeper

# Start the service
docker compose up -d linkedin-keeper

# Verify it's running
docker compose ps linkedin-keeper
docker compose logs -f linkedin-keeper
```

### Step 2: Open Firewall Ports

Open the required ports in GCP firewall:

```bash
# Port 3001 - Session Keeper API
gcloud compute firewall-rules create allow-linkedin-keeper-api \
    --allow tcp:3001 \
    --source-ranges 0.0.0.0/0 \
    --description "Allow LinkedIn Keeper API" \
    --target-tags multiuser

# Port 6080 - noVNC Web Interface
gcloud compute firewall-rules create allow-linkedin-keeper-novnc \
    --allow tcp:6080 \
    --source-ranges 0.0.0.0/0 \
    --description "Allow LinkedIn Keeper noVNC" \
    --target-tags multiuser

# Port 5901 - VNC (optional, for VNC clients)
gcloud compute firewall-rules create allow-linkedin-keeper-vnc \
    --allow tcp:5901 \
    --source-ranges 0.0.0.0/0 \
    --description "Allow LinkedIn Keeper VNC" \
    --target-tags multiuser
```

### Step 3: Access the Session Keeper

1. **Web UI**: `http://34.131.105.19:3001`
2. **noVNC**: `http://34.131.105.19:6080`
3. **VNC Client**: `vnc://34.131.105.19:5901`

### Step 4: First Run - Manual Login

1. Open the web UI: `http://34.131.105.19:3001`
2. Click **"Start Automation"**
3. Click **"Open Browser Console (noVNC)"**
4. In the noVNC window, you'll see a browser opening LinkedIn
5. **Log in to LinkedIn manually** using your credentials
6. **Navigate to your feed** (`https://www.linkedin.com/feed`)
7. The session will be automatically saved

### Step 5: Verify Session is Saved

Check the logs:

```bash
docker compose logs linkedin-keeper | grep -i "session saved\|login detected"
```

You should see:
```
Login detected; session saved to linkedin-profile.
```

### Step 6: Test Session Reuse

1. Click **"Clear Saved Session"** (to test from scratch)
2. Click **"Start Automation"** again
3. This time it should load the feed automatically without requiring login

## Usage Workflow

### Normal Operation

1. **Start the session keeper** (once per deployment):
   ```bash
   docker compose up -d linkedin-keeper
   ```

2. **Access the web UI**: `http://34.131.105.19:3001`

3. **First time setup**:
   - Click "Start Automation"
   - Click "Open Browser Console (noVNC)"
   - Log in to LinkedIn manually
   - Navigate to feed

4. **Subsequent runs**:
   - Session is automatically loaded
   - Feed opens in headless mode
   - Keep-alive refreshes every 20 minutes

### Session Management

- **Clear session**: Click "Clear Saved Session" to force re-login
- **View browser**: Click "Open Browser Console (noVNC)" anytime
- **Check status**: Monitor the status display in the web UI

## Integration with Campaign Automation

The saved LinkedIn session can be used by your campaign automation:

1. **Session Storage**: Browser profile saved in `linkedin_profile` volume
2. **Cookie Access**: Cookies can be extracted from the persistent context
3. **Reuse in Campaigns**: The saved session is used for all LinkedIn automation

### Future Integration Steps

To fully integrate with the existing campaign system:

1. **Extract cookies from linkedin-keeper**:
   - Add an API endpoint to export cookies
   - Store cookies in the database as a LinkedIn account

2. **Update campaign tasks**:
   - Use the saved browser profile instead of creating new contexts
   - Connect to the persistent context for automation

3. **Deprecate old VNC session manager**:
   - Remove `vnc_session_manager.py`
   - Remove `vnc_sessions.py` API endpoints
   - Update accounts page to use linkedin-keeper

## Troubleshooting

### Service won't start

```bash
# Check logs
docker compose logs linkedin-keeper

# Check if ports are in use
sudo netstat -tlnp | grep -E '3001|5901|6080'

# Restart service
docker compose restart linkedin-keeper
```

### noVNC connection fails

```bash
# Check if websockify is running
docker exec multiuser-linkedin-keeper-1 ps aux | grep websockify

# Check Xvfb
docker exec multiuser-linkedin-keeper-1 ps aux | grep Xvfb

# View Xvfb logs
docker exec multiuser-linkedin-keeper-1 cat /tmp/xvfb.log
```

### Session not saving

```bash
# Check profile directory
docker exec multiuser-linkedin-keeper-1 ls -la /app/linkedin-profile/

# Check for Chromium locks
docker exec multiuser-linkedin-keeper-1 ls -la /app/linkedin-profile/ | grep Singleton

# Clear locks manually
docker exec multiuser-linkedin-keeper-1 rm -f /app/linkedin-profile/Singleton*
docker compose restart linkedin-keeper
```

### Browser crashes

```bash
# Increase shared memory in docker-compose.yml
# Already set to 2GB, but can increase if needed:
shm_size: '4gb'

# Restart after changing
docker compose up -d linkedin-keeper
```

## Architecture Comparison

### Old Approach (vnc-browser)
- Separate VNC container with Chrome
- Backend connects via CDP
- Manual session management
- No automatic keep-alive
- Complex multi-container setup

### New Approach (linkedin-keeper)
- Single container with Playwright + VNC
- Persistent browser context
- Automatic first-run detection
- Built-in keep-alive (20 min intervals)
- Simpler, more maintainable

## Next Steps

1. **Deploy and test** the linkedin-keeper service
2. **Verify manual login** works via noVNC
3. **Test session persistence** across restarts
4. **Integrate with campaigns** (extract cookies, use in automation)
5. **Deprecate old code** (vnc_session_manager, vnc_sessions API)
6. **Update frontend** accounts page to use linkedin-keeper

## Environment Variables

Set these in your `.env` file or docker-compose.yml:

```bash
# LinkedIn Keeper
LINKEDIN_KEEPER_PORT=3001
LINKEDIN_KEEPER_HEADLESS=false  # false for first run, true for production
LINKEDIN_KEEPER_FRONTEND_ORIGIN=*  # or specific domain for CORS
```

## Security Considerations

1. **VNC is not password-protected** - Add password or restrict via firewall
2. **noVNC should be behind auth** in production
3. **Firewall rules** should restrict access to trusted IPs
4. **LinkedIn credentials** are never stored - only cookies/session data

## Support

For issues or questions:
1. Check logs: `docker compose logs linkedin-keeper`
2. Review README: `linkedin-keeper/README.md`
3. Verify ports are open and accessible
4. Ensure VM has sufficient resources (2GB RAM minimum for Chromium)
