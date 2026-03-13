// Minimal LinkedIn session keeper with a tiny frontend
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PROFILE_DIR = path.join(process.cwd(), 'linkedin-profile');
const KEEP_ALIVE_MS = 20 * 60 * 1000; // 20 minutes
const PORT = Number(process.env.PORT) || 3001;
const FRONTEND_ORIGIN = process.env.FRONTEND_ORIGIN || '*';
const HEADLESS_ENV = process.env.HEADLESS;

function checkFirstRun() {
  const exists = fs.existsSync(PROFILE_DIR);
  console.log(`Checking profile directory: ${PROFILE_DIR}, exists: ${exists}`);
  
  if (!exists) {
    return true;
  }
  
  const cookiesPath = path.join(PROFILE_DIR, 'Default', 'Cookies');
  const hasCookies = fs.existsSync(cookiesPath);
  console.log(`LinkedIn cookies exist: ${hasCookies}`);
  
  if (hasCookies) {
    try {
      const cookieContent = fs.readFileSync(cookiesPath, 'utf8');
      const hasLinkedInCookies = cookieContent.includes('linkedin') || cookieContent.includes('li_at');
      console.log(`LinkedIn-specific cookies found: ${hasLinkedInCookies}`);
      return !hasLinkedInCookies;
    } catch (err) {
      console.log('Could not read cookies file, assuming first run');
      return true;
    }
  }
  
  return true;
}

async function clearSession() {
  try {
    if (context) {
      try {
        await context.close();
      } catch (_) {}
      context = null;
    }
    if (keepAliveTimer) {
      clearInterval(keepAliveTimer);
      keepAliveTimer = null;
    }
    automationState = 'idle';

    const lockFiles = ['SingletonLock', 'SingletonSocket', 'SingletonCookie'];
    const removeLocks = () => {
      for (const lock of lockFiles) {
        const p = path.join(PROFILE_DIR, lock);
        if (fs.existsSync(p)) {
          try { fs.rmSync(p, { force: true }); } catch (_) {}
        }
      }
    };

    const removeProfile = () => {
      if (fs.existsSync(PROFILE_DIR)) {
        try {
          fs.rmSync(PROFILE_DIR, { recursive: true, force: true });
          return;
        } catch (err) {
          if (err.code !== 'EBUSY') throw err;
          const tempDir = `${PROFILE_DIR}-old-${Date.now()}`;
          fs.renameSync(PROFILE_DIR, tempDir);
          fs.rmSync(tempDir, { recursive: true, force: true });
        }
      }
    };

    let attempts = 0;
    while (attempts < 3) {
      try {
        removeLocks();
        removeProfile();
        break;
      } catch (err) {
        attempts += 1;
        if (attempts >= 3) throw err;
        await new Promise((r) => setTimeout(r, 300));
      }
    }

    return { message: 'Saved session cleared. Next run will be headful for login.' };
  } catch (err) {
    return { error: err.message || 'Failed to clear session.' };
  }
}

let context = null;
let page = null;
let keepAliveTimer = null;
let automationState = 'idle';

function resolveHeadless(isFirst) {
  if (HEADLESS_ENV === 'true') return true;
  if (HEADLESS_ENV === 'false') return false;
  return isFirst ? false : true;
}

function applyCors(res) {
  res.setHeader('Access-Control-Allow-Origin', FRONTEND_ORIGIN);
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

function send(res, status, body, headers = {}) {
  const data = typeof body === 'string' ? body : JSON.stringify(body);
  const finalHeaders = {
    'Content-Type': typeof body === 'string' ? 'text/html; charset=utf-8' : 'application/json',
    'Content-Length': Buffer.byteLength(data),
    ...headers,
  };
  applyCors(res);
  res.writeHead(status, finalHeaders);
  res.end(data);
}

function serveIndex(res) {
  const filePath = path.join(process.cwd(), 'public', 'index.html');
  if (!fs.existsSync(filePath)) {
    send(res, 404, 'Frontend missing');
    return;
  }
  const content = fs.readFileSync(filePath, 'utf8');
  send(res, 200, content, { 'Content-Type': 'text/html; charset=utf-8' });
}

async function startAutomation() {
  if (automationState === 'running') {
    return { message: 'Automation already running.' };
  }
  if (automationState === 'starting') {
    return { message: 'Automation is starting, please wait...' };
  }

  automationState = 'starting';

  try {
    const isFirstRun = checkFirstRun();
    console.log(`First run: ${isFirstRun} (profile exists: ${fs.existsSync(PROFILE_DIR)})`);

    context = await chromium.launchPersistentContext(PROFILE_DIR, {
      headless: resolveHeadless(isFirstRun),
      viewport: { width: 1280, height: 720 },
      args: ['--disable-dev-shm-usage', '--no-sandbox'],
    });

    page = context.pages()[0] || (await context.newPage());

    if (isFirstRun) {
      console.log('First run detected. Opening LinkedIn homepage for manual login...');
      await page.goto('https://www.linkedin.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
      console.log('LinkedIn homepage loaded. Please log in via VNC (port 5901) and navigate to your feed.');
      await page.waitForURL('**/feed*', { timeout: 0 });
      console.log('Login detected; session saved to linkedin-profile.');
    } else {
      console.log('Attempting to load LinkedIn feed with saved session...');
      await page.goto('https://www.linkedin.com/feed', { waitUntil: 'domcontentloaded', timeout: 60000 });
      if (page.url().includes('/feed')) {
        console.log('Session active');
      } else {
        console.log('Feed not reachable with saved session. Falling back to login flow...');
        await page.goto('https://www.linkedin.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
        console.log('Please log in via VNC (port 5901) and navigate to your feed.');
        await page.waitForURL('**/feed*', { timeout: 0 });
        console.log('Login detected; session updated.');
      }
    }

    if (keepAliveTimer) clearInterval(keepAliveTimer);
    keepAliveTimer = setInterval(async () => {
      try {
        if (page) {
          await page.reload({ waitUntil: 'networkidle' });
          console.log('Keep-alive refresh at', new Date().toISOString());
        }
      } catch (err) {
        console.error('Keep-alive failed:', err);
      }
    }, KEEP_ALIVE_MS);

    automationState = 'running';
    return { message: 'Session active. Keep-alive enabled.' };
  } catch (err) {
    automationState = 'idle';
    if (keepAliveTimer) {
      clearInterval(keepAliveTimer);
      keepAliveTimer = null;
    }
    if (context) {
      try {
        await context.close();
      } catch (closeErr) {
        console.error('Error during context close:', closeErr);
      }
    }
    context = null;
    page = null;
    throw err;
  }
}

function registerShutdown() {
  const shutdown = async () => {
    if (keepAliveTimer) clearInterval(keepAliveTimer);
    if (context) {
      try {
        await context.close();
      } catch (err) {
        console.error('Error closing context on shutdown:', err);
      }
    }
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

function createServer() {
  return http.createServer(async (req, res) => {
    applyCors(res);

    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    if (req.method === 'GET' && req.url === '/') {
      serveIndex(res);
      return;
    }

    if (req.method === 'POST' && req.url === '/clear') {
      const result = await clearSession();
      const status = result.error ? 500 : 200;
      send(res, status, result);
      return;
    }

    if (req.method === 'POST' && req.url === '/start') {
      try {
        const result = await startAutomation();
        send(res, 200, result);
      } catch (err) {
        console.error('Automation failed:', err);
        send(res, 500, { error: err.message || 'Unknown error' });
      }
      return;
    }

    if (req.method === 'GET' && req.url === '/session-info') {
      if (!context || !page) {
        return send(res, 200, { has_session: false });
      }
      try {
        // Check if we're logged in by visiting LinkedIn feed
        const currentUrl = page.url();
        const isLoggedIn = currentUrl.includes('linkedin.com') && !currentUrl.includes('login');
        
        // Try to get email from LinkedIn profile if logged in
        let email = 'keeper-session@example.com';
        if (isLoggedIn) {
          try {
            await page.goto('https://www.linkedin.com/me/profile-views/', { waitUntil: 'domcontentloaded', timeout: 5000 });
            const emailElement = await page.locator('.pv-text-details__left-panel .text-body-medium').first();
            if (await emailElement.count() > 0) {
              email = await emailElement.textContent() || email;
            }
          } catch (e) {
            console.log('Could not extract email, using default');
          }
        }
        
        send(res, 200, { has_session: isLoggedIn, email });
      } catch (err) {
        send(res, 200, { has_session: false, error: err.message });
      }
      return;
    }

    if (req.method === 'GET' && req.url === '/export-cookies') {
      if (!context) {
        return send(res, 400, 'No active session');
      }
      try {
        const cookies = await context.cookies();
        send(res, 200, JSON.stringify(cookies, null, 2), { 'Content-Type': 'application/json' });
      } catch (err) {
        send(res, 500, { error: err.message || 'Failed to export cookies' });
      }
      return;
    }

    send(res, 404, { error: 'Not found' });
  });
}

async function main() {
  registerShutdown();
  const server = createServer();
  server.listen(PORT, () => {
    console.log(`UI available at http://localhost:${PORT}`);
  });
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
