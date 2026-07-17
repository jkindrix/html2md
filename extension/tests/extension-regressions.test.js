const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const extensionRoot = path.resolve(__dirname, '..');
const { normalizeExtractedHtml } = require('../conversion-utils.js');

test('normalizes short and malformed extracted HTML without reassigning inputs', () => {
  const complete = '<html><body>' + 'content '.repeat(20) + '</body></html>';
  assert.equal(normalizeExtractedHtml(complete), complete);

  for (const fragment of ['<p>short</p>', 'plain malformed content']) {
    const normalized = normalizeExtractedHtml(fragment);
    assert.match(normalized, /^<!DOCTYPE html>/);
    assert.ok(normalized.includes(fragment));
  }

  for (const empty of ['', '   ', null]) {
    assert.throws(() => normalizeExtractedHtml(empty), /non-empty string/);
  }
});

test('popup loads only the generic conversion stack', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const scripts = [...popup.matchAll(/<script src="([^"]+)"><\/script>/g)]
    .map(match => match[1]);

  assert.deepEqual(scripts, [
    'logger.js',
    'turndown.js',
    'conversion-utils.js',
    'popup.js'
  ]);
});

test('article mode uses the pinned packaged Mozilla Readability asset', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');
  const readability = fs.readFileSync(path.join(extensionRoot, 'readability.js'));

  assert.ok(!popup.includes('id="trim-content"'));
  assert.match(popupScript, /files: \['readability\.js'\]/);
  assert.match(popupScript, /new Readability\(document\.cloneNode\(true\)\)\.parse\(\)/);
  assert.doesNotMatch(popupScript, /\.post-content|\.article-content|elementsToRemove/);
  assert.equal(
    crypto.createHash('sha256').update(readability).digest('hex'),
    '34dcab3d0832d0019f02990eed6b6124e029e8c32b9f0c6f2550544ff8dff174'
  );
});

test('unsupported URL and element modes are not exposed', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const manifest = JSON.parse(fs.readFileSync(path.join(extensionRoot, 'manifest.json'), 'utf8'));

  assert.ok(!popup.includes('id="url-capture-tab"'));
  assert.ok(!popup.includes('id="scan-urls-button"'));
  assert.ok(!popup.includes('<option value="element">'));
  assert.equal(manifest.background, undefined);
  assert.ok(!fs.existsSync(path.join(extensionRoot, 'background.js')));
});

test('supported popup preview uses packaged scripts without inline JavaScript', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const scripts = [...popup.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)];

  assert.ok(popup.includes('id="markdown-result"'));
  assert.ok(popup.includes('<option value="show">Show in Popup</option>'));
  assert.ok(scripts.length > 0);
  for (const script of scripts) {
    assert.match(script[1], /\ssrc="[^"]+"/);
    assert.equal(script[2].trim(), '');
  }
});

test('manifest and controls use the documented least-privilege surface', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(extensionRoot, 'manifest.json'), 'utf8'));
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');

  assert.deepEqual(
    [...manifest.permissions].sort(),
    ['activeTab', 'clipboardWrite', 'downloads', 'scripting', 'storage'].sort()
  );
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.web_accessible_resources, undefined);
  assert.ok(!popup.includes('cli-path'));
  assert.ok(!popupScript.includes('cliPath'));
  assert.ok(!popup.includes('stop-capture'));

  const ids = [...popup.matchAll(/\sid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length);
});

test('project-authored production scripts contain no direct console logging or duplicate worker conversion', () => {
  for (const filename of fs.readdirSync(extensionRoot).filter(name => {
    return name.endsWith('.js') && name !== 'readability.js';
  })) {
    const source = fs.readFileSync(path.join(extensionRoot, filename), 'utf8');
    assert.doesNotMatch(source, /console\.(?:log|warn|error)/);
    assert.doesNotMatch(source, /Justin(?:'s)? Workspace/i);
  }

  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');
  assert.equal((popupScript.match(/function convertToMarkdown\(/g) || []).length, 1);
});
