const assert = require('node:assert/strict');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const extensionRoot = path.resolve(__dirname, '..');

class CdpClient {
  constructor(url) {
    this.url = url;
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    this.socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
        return;
      }

      for (const listener of this.listeners.get(message.method) || []) {
        listener(message.params);
      }
    };
    await new Promise((resolve, reject) => {
      this.socket.onopen = resolve;
      this.socket.onerror = reject;
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket?.close();
  }
}

function findBrowser() {
  const candidates = [
    process.env.CHROME_BIN,
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable'
  ].filter(Boolean);
  const browser = candidates.find(candidate => fs.existsSync(candidate));
  if (!browser) throw new Error('No supported Chromium executable found');
  return browser;
}

async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function waitFor(callback, description, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await callback();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${description}${lastError ? `: ${lastError.message}` : ''}`);
}

async function createTarget(port, url) {
  const response = await fetch(
    `http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`,
    { method: 'PUT' }
  );
  if (!response.ok) throw new Error(`Could not create Chromium target: ${response.status}`);
  return response.json();
}

async function evaluate(client, expression, options = {}) {
  const result = await client.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    ...options
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  }
  return result.result.value;
}

async function main() {
  const xvfb = spawnSync('which', ['xvfb-run'], { encoding: 'utf8' }).stdout.trim();
  if (!xvfb) throw new Error('xvfb-run is required for unpacked-extension tests');

  const browser = findBrowser();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'html2md-chromium-'));
  const downloads = path.join(profile, 'downloads');
  fs.mkdirSync(downloads);
  const port = await unusedPort();
  const child = spawn(
    xvfb,
    [
      '-a',
      browser,
      '--no-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--no-first-run',
      '--disable-default-apps',
      `--user-data-dir=${profile}`,
      `--remote-debugging-port=${port}`,
      `--disable-extensions-except=${extensionRoot}`,
      `--load-extension=${extensionRoot}`,
      'about:blank'
    ],
    { detached: true, stdio: ['ignore', 'ignore', 'pipe'], env: { ...process.env, HOME: profile } }
  );

  let browserClient;
  let popupClient;
  let fixtureClient;
  try {
    const version = await waitFor(async () => {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      return response.ok ? response.json() : null;
    }, 'Chromium DevTools');

    const preferencesPath = path.join(profile, 'Default', 'Preferences');
    const extensionId = await waitFor(() => {
      if (!fs.existsSync(preferencesPath)) return null;
      const preferences = JSON.parse(fs.readFileSync(preferencesPath, 'utf8'));
      const settings = preferences.extensions?.settings || {};
      return Object.entries(settings).find(([_id, value]) => {
        return value.path && path.resolve(value.path) === extensionRoot;
      })?.[0];
    }, 'the unpacked extension registration');

    browserClient = new CdpClient(version.webSocketDebuggerUrl);
    await browserClient.connect();
    await browserClient.send('Browser.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: downloads,
      eventsEnabled: true
    });

    const popupTarget = await createTarget(
      port,
      `chrome-extension://${extensionId}/popup.html`
    );
    popupClient = new CdpClient(popupTarget.webSocketDebuggerUrl);
    await popupClient.connect();

    const exceptions = [];
    popupClient.on('Runtime.exceptionThrown', event => exceptions.push(event));
    await popupClient.send('Runtime.enable');
    await popupClient.send('Page.enable');
    await popupClient.send('Page.reload');
    await waitFor(
      () => evaluate(popupClient, 'document.readyState === "complete"'),
      'popup reload'
    );

    assert.equal(await evaluate(popupClient, 'typeof TurndownService'), 'function');
    assert.equal(await evaluate(popupClient, 'typeof Html2MdLogger'), 'object');
    assert.equal(
      await evaluate(popupClient, 'new Set([...document.querySelectorAll("[id]")].map(node => node.id)).size === document.querySelectorAll("[id]").length'),
      true
    );

    await evaluate(popupClient, `settingsBtn.click()`);
    assert.equal(
      await evaluate(popupClient, `document.getElementById('settings').classList.contains('active')`),
      true
    );
    await evaluate(
      popupClient,
      `document.getElementById('heading-style').value = 'setext'; saveSettingsBtn.click()`
    );
    await waitFor(async () => {
      const stored = await evaluate(
        popupClient,
        `new Promise(resolve => chrome.storage.sync.get('html2mdSettings', resolve))`
      );
      return stored.html2mdSettings?.markdownOptions?.headingStyle === 'setext';
    }, 'saved popup settings');
    await evaluate(popupClient, `themeToggleBtn.click()`);
    assert.equal(await evaluate(popupClient, `document.body.classList.contains('dark-theme')`), true);
    await evaluate(popupClient, `window.confirm = () => true; resetDefaultsBtn.click()`);
    assert.equal(await evaluate(popupClient, `document.getElementById('heading-style').value`), 'atx');

    const markdown = await evaluate(
      popupClient,
      `convertToMarkdown('<h1>Fixture</h1><p>Search indexing uses a model.</p><pre><code class="language-text">model Search API</code></pre>')`
    );
    assert.match(markdown, /^# Fixture/m);
    assert.match(markdown, /Search indexing uses a model\./);
    assert.match(markdown, /```text\nmodel Search API\n```/);

    const articleText = 'A substantial article sentence with concrete evidence and punctuation. '.repeat(12);
    const fixtureHtml = `<html><body><nav>Full navigation</nav><article><h1>Injected Article</h1><p id="selection">Selected text. ${articleText}</p><p>${articleText}</p></article><section class="comments">Full comments</section><footer>Full footer</footer></body></html>`;
    const fixtureTarget = await createTarget(
      port,
      `data:text/html,${encodeURIComponent(fixtureHtml)}`
    );
    fixtureClient = new CdpClient(fixtureTarget.webSocketDebuggerUrl);
    await fixtureClient.connect();
    await fixtureClient.send('Runtime.enable');
    const readabilitySource = fs.readFileSync(path.join(extensionRoot, 'readability.js'), 'utf8');
    await evaluate(fixtureClient, readabilitySource);
    assert.equal(await evaluate(fixtureClient, 'typeof Readability'), 'function');
    const extractionSource = await evaluate(popupClient, 'extractPageContent.toString()');
    const fullPage = await evaluate(fixtureClient, `(${extractionSource})('full-page')`);
    const article = await evaluate(fixtureClient, `(${extractionSource})('article')`);
    assert.match(fullPage, /<nav>Full navigation<\/nav>/);
    assert.match(fullPage, /Full comments/);
    assert.match(fullPage, /<footer>Full footer<\/footer>/);
    assert.doesNotMatch(article, /Full navigation|Full comments|Full footer/);
    assert.match(article, /<h[12]>Injected Article<\/h[12]>/);

    const fullMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(fullPage)})`
    );
    assert.match(fullMarkdown, /Full navigation/);
    assert.match(fullMarkdown, /Full comments/);
    assert.match(fullMarkdown, /Full footer/);

    await evaluate(
      fixtureClient,
      `const range = document.createRange();
       range.selectNodeContents(document.getElementById('selection'));
       const selection = window.getSelection();
       selection.removeAllRanges();
       selection.addRange(range);`
    );
    const selection = await evaluate(fixtureClient, `(${extractionSource})('selection')`);
    assert.match(selection, /Selected text/);
    assert.doesNotMatch(selection, /Injected Article/);

    const turndownSource = fs.readFileSync(path.join(extensionRoot, 'turndown.js'), 'utf8');
    await evaluate(fixtureClient, turndownSource);
    const injectedMarkdown = await evaluate(
      fixtureClient,
      `new TurndownService().turndown(${JSON.stringify(article)})`
    );
    assert.match(injectedMarkdown, /Injected/);

    await evaluate(popupClient, `handleOutput('# Preview result', 'show', 'Fixture')`);
    assert.deepEqual(
      await evaluate(popupClient, `({ text: markdownResult.textContent, visible: resultContainer.style.display })`),
      { text: '# Preview result', visible: 'block' }
    );

    await popupClient.send('Page.bringToFront');
    await evaluate(
      popupClient,
      `handleOutput('# Copy result', 'copy', 'Fixture')`,
      { userGesture: true }
    );
    assert.equal(await evaluate(popupClient, `statusMessage.textContent`), 'Copied to clipboard');

    const permissions = await evaluate(
      popupClient,
      'new Promise(resolve => chrome.permissions.getAll(resolve))'
    );
    assert.deepEqual(permissions.origins, []);
    assert.deepEqual(
      [...permissions.permissions].sort(),
      ['activeTab', 'clipboardWrite', 'downloads', 'scripting', 'storage'].sort()
    );

    const denied = await evaluate(
      popupClient,
      `new Promise(resolve => chrome.tabs.query({}, tabs => {
        const target = tabs.find(tab => !tab.active);
        chrome.scripting.executeScript(
          { target: { tabId: target.id }, func: () => document.title },
          result => resolve({ result, error: chrome.runtime.lastError?.message || null })
        );
      }))`
    );
    assert.match(denied.error, /Cannot access contents|respective host/);

    await evaluate(popupClient, `handleOutput('# Download result', 'show', 'Fixture')`);
    const downloadResult = await evaluate(
      popupClient,
      `downloadMarkdown(null, 'Fixture Page')`,
      { userGesture: true }
    );
    assert.equal(downloadResult.error, null);
    assert.equal(typeof downloadResult.downloadId, 'number');
    await new Promise(resolve => setTimeout(resolve, 1000));
    const downloadItems = await evaluate(
      popupClient,
      `new Promise(resolve => chrome.downloads.search({}, resolve))`
    );
    const downloaded = downloadItems.find(item => {
      return item.byExtensionId === extensionId && item.mime === 'text/markdown';
    });
    assert.ok(downloaded, `download was not recorded: ${JSON.stringify(downloadItems)}`);
    assert.equal(downloaded.state, 'complete', JSON.stringify(downloaded));
    assert.match(fs.readFileSync(downloaded.filename, 'utf8'), /Download result/);

    await new Promise(resolve => setTimeout(resolve, 250));
    assert.equal(exceptions.length, 0, 'popup raised a runtime exception after reload');
    process.stdout.write('Chromium extension smoke: popup controls, extraction, conversion, output, and permissions passed\n');
  } finally {
    popupClient?.close();
    fixtureClient?.close();
    browserClient?.close();
    try {
      process.kill(-child.pid, 'SIGTERM');
    } catch (_error) {
      child.kill('SIGTERM');
    }
    await new Promise(resolve => setTimeout(resolve, 250));
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
