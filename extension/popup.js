// DOM Elements
const convertBtn = document.getElementById('convert-btn');
const settingsBtn = document.getElementById('settings-btn');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const conversionModeSelect = document.getElementById('conversion-mode');
const trimContentCheckbox = document.getElementById('trim-content');
const outputActionSelect = document.getElementById('output-action');
const resultContainer = document.getElementById('result-container');
const markdownResult = document.getElementById('markdown-result');
const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');
const statusMessage = document.getElementById('status-message');
const spinner = document.getElementById('spinner');
const settingsModal = document.getElementById('settings-modal');
const closeModalBtn = document.querySelector('.close');
const saveSettingsBtn = document.getElementById('save-settings');
const resetDefaultsBtn = document.getElementById('reset-defaults');
const cliLink = document.getElementById('cli-link');

// Default settings
const defaultSettings = {
  theme: 'light',
  markdownOptions: {
    headingStyle: 'atx',
    linkStyle: 'inline',
    bulletMarker: '-',
  },
  contentOptions: {
    preserveImages: true,
    includeTables: true,
    codeBlocks: true,
    inlineLinks: true
  },
  cliPath: ''
};

// Current settings - will be loaded from storage
let settings = {...defaultSettings};

// Initialize TurndownService for HTML to Markdown conversion
let turndownService;

// Initialize the extension
document.addEventListener('DOMContentLoaded', () => {
  // Load saved settings
  loadSettings();

  // Initialize the UI
  initializeUI();

  // Set up event listeners
  setupEventListeners();
});

// Load saved settings from Chrome storage
function loadSettings() {
  chrome.storage.sync.get('html2mdSettings', (data) => {
    if (data.html2mdSettings) {
      settings = {...defaultSettings, ...data.html2mdSettings};
    }

    // Apply loaded settings to the UI
    applySettings();
  });
}

// Save settings to Chrome storage
function saveSettings() {
  chrome.storage.sync.set({ html2mdSettings: settings }, () => {
    showStatus('Settings saved', 'success');
  });
}

// Apply current settings to the UI
function applySettings() {
  // Apply theme
  if (settings.theme === 'dark') {
    document.body.classList.add('dark-theme');
    document.getElementById('light-icon').style.display = 'none';
    document.getElementById('dark-icon').style.display = 'block';
  } else {
    document.body.classList.remove('dark-theme');
    document.getElementById('light-icon').style.display = 'block';
    document.getElementById('dark-icon').style.display = 'none';
  }

  // Set form values based on settings
  document.getElementById('heading-style').value = settings.markdownOptions.headingStyle;
  document.getElementById('link-style').value = settings.markdownOptions.linkStyle;
  document.getElementById('bullet-marker').value = settings.markdownOptions.bulletMarker;

  document.getElementById('preserve-images').checked = settings.contentOptions.preserveImages;
  document.getElementById('include-tables').checked = settings.contentOptions.includeTables;
  document.getElementById('code-blocks').checked = settings.contentOptions.codeBlocks;
  document.getElementById('inline-links').checked = settings.contentOptions.inlineLinks;

  document.getElementById('cli-path').value = settings.cliPath || '';

  // Initialize Turndown with current settings
  initializeTurndown();
}

// Initialize the Turndown service with current settings
function initializeTurndown() {
  turndownService = new TurndownService({
    headingStyle: settings.markdownOptions.headingStyle,
    bulletListMarker: settings.markdownOptions.bulletMarker,
    linkStyle: settings.markdownOptions.linkStyle,
    codeBlockStyle: settings.contentOptions.codeBlocks ? 'fenced' : 'indented'
  });

  // Configure Turndown based on settings
  if (!settings.contentOptions.preserveImages) {
    turndownService.remove('img');
  }

  if (settings.contentOptions.includeTables) {
    turndownService.keep(['table', 'tr', 'td', 'th', 'thead', 'tbody']);
  }
}

// Initialize UI elements
function initializeUI() {
  // Set chrome extension version in the CLI link
  chrome.management.getSelf((info) => {
    cliLink.setAttribute('title', `Download HTML2MD CLI Tool v${info.version}`);
  });
}

// Set up all event listeners
function setupEventListeners() {
  // Main convert button
  convertBtn.addEventListener('click', handleConversion);

  // Settings button (opens modal)
  settingsBtn.addEventListener('click', () => {
    settingsModal.style.display = 'block';
  });

  // Close modal button
  closeModalBtn.addEventListener('click', () => {
    settingsModal.style.display = 'none';
  });

  // Also close when clicking outside the modal
  window.addEventListener('click', (event) => {
    if (event.target === settingsModal) {
      settingsModal.style.display = 'none';
    }
  });

  // Save settings button
  saveSettingsBtn.addEventListener('click', () => {
    updateSettingsFromForm();
    saveSettings();
    settingsModal.style.display = 'none';
  });

  // Reset defaults button
  resetDefaultsBtn.addEventListener('click', () => {
    if (confirm('Are you sure you want to reset all settings to default values?')) {
      settings = {...defaultSettings};
      applySettings();
      saveSettings();
      showStatus('Settings reset to defaults', 'success');
    }
  });

  // Theme toggle
  themeToggleBtn.addEventListener('click', () => {
    settings.theme = settings.theme === 'light' ? 'dark' : 'light';
    applySettings();
    saveSettings();
  });

  // Copy button
  copyBtn.addEventListener('click', () => {
    const markdownText = markdownResult.textContent;
    navigator.clipboard.writeText(markdownText).then(() => {
      showStatus('Copied to clipboard', 'success');
    }).catch(err => {
      showStatus('Failed to copy: ' + err, 'error');
    });
  });

  // Download button
  downloadBtn.addEventListener('click', () => {
    downloadMarkdown();
  });

  // CLI link
  cliLink.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'https://github.com/jkindrix/html2md' });
  });
}

// Update settings object from form values
function updateSettingsFromForm() {
  settings.markdownOptions = {
    headingStyle: document.getElementById('heading-style').value,
    linkStyle: document.getElementById('link-style').value,
    bulletMarker: document.getElementById('bullet-marker').value
  };

  settings.contentOptions = {
    preserveImages: document.getElementById('preserve-images').checked,
    includeTables: document.getElementById('include-tables').checked,
    codeBlocks: document.getElementById('code-blocks').checked,
    inlineLinks: document.getElementById('inline-links').checked
  };

  settings.cliPath = document.getElementById('cli-path').value;

  // Reinitialize Turndown with new settings
  initializeTurndown();
}

// Handle the conversion process
function handleConversion() {
  const conversionMode = conversionModeSelect.value;
  const trimContent = trimContentCheckbox.checked;
  const outputAction = outputActionSelect.value;

  showStatus('Converting...', 'processing');
  showSpinner(true);

  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];

    // Inject content script to extract HTML
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: extractPageContent,
      args: [conversionMode, trimContent]
    }, (results) => {
      if (chrome.runtime.lastError) {
        showStatus('Error: ' + chrome.runtime.lastError.message, 'error');
        showSpinner(false);
        return;
      }

      const htmlContent = results[0].result;

      if (!htmlContent) {
        showStatus('Error: Could not extract content', 'error');
        showSpinner(false);
        return;
      }

      // Convert HTML to Markdown
      const markdown = convertToMarkdown(htmlContent, trimContent);

      // Handle the output based on user selection
      handleOutput(markdown, outputAction, tab.title);

      showStatus('Conversion complete', 'success');
      showSpinner(false);
    });
  });
}

// Extract content from the page based on mode
function extractPageContent(mode, trim) {
  let content = '';

  switch(mode) {
    case 'full-page':
      content = document.documentElement.outerHTML;
      break;
    case 'selection':
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const fragment = range.cloneContents();
        const div = document.createElement('div');
        div.appendChild(fragment);
        content = div.innerHTML;
      } else {
        content = document.documentElement.outerHTML;
      }
      break;
    case 'article':
      // Try to find the main content
      const article = document.querySelector('article') ||
                      document.querySelector('main') ||
                      document.querySelector('.post-content') ||
                      document.querySelector('.article-content') ||
                      document.querySelector('#content');

      if (article) {
        content = article.outerHTML;
      } else {
        // If no main content container is found, use the full page
        content = document.documentElement.outerHTML;
      }
      break;
  }

  return content;
}

// Convert HTML to Markdown using TurndownService
function convertToMarkdown(html, trim) {
  // Perform any pre-processing if trim is enabled
  if (trim) {
    // Simple trimming: remove scripts, styles, nav, footer, etc.
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;

    // Remove unwanted elements
    const elementsToRemove = [
      'script', 'style', 'iframe', 'noscript',
      'nav:not([role="navigation"])',
      'footer',
      '[role="complementary"]',
      '[role="banner"]',
      '.sidebar', '.widget', '.cookie-notice',
      '#comments', '.comments', '.related-posts',
      'aside', '.ad', '.advertisement', '.social-share',
      '.navigation', '.pagination'
    ];

    elementsToRemove.forEach(selector => {
      tempDiv.querySelectorAll(selector).forEach(el => {
        el.remove();
      });
    });

    html = tempDiv.innerHTML;
  }

  return turndownService.turndown(html);
}

// Handle the output based on selected action
function handleOutput(markdown, action, pageTitle) {
  switch(action) {
    case 'show':
      // Show in popup
      markdownResult.textContent = markdown;
      resultContainer.style.display = 'block';
      break;
    case 'download':
      // Download as file
      downloadMarkdown(markdown, pageTitle);
      break;
    case 'copy':
      // Copy to clipboard
      navigator.clipboard.writeText(markdown).then(() => {
        showStatus('Copied to clipboard', 'success');
      }).catch(err => {
        showStatus('Failed to copy: ' + err, 'error');
      });
      break;
  }
}

// Download markdown as a file
function downloadMarkdown(markdown = null, pageTitle = 'page') {
  // If markdown is not provided, use the one from the result container
  if (!markdown) {
    markdown = markdownResult.textContent;
  }

  // Clean the filename
  let filename = pageTitle
    .toLowerCase()
    .replace(/[^\w\s]/gi, '')
    .replace(/\s+/g, '-')
    .substring(0, 50);

  filename = filename || 'converted-page';
  filename += '.md';

  // Create and trigger download
  const blob = new Blob([markdown], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);

  chrome.downloads.download({
    url: url,
    filename: filename,
    saveAs: true
  }, (downloadId) => {
    if (chrome.runtime.lastError) {
      showStatus('Error saving file: ' + chrome.runtime.lastError.message, 'error');
    } else {
      showStatus('File saved', 'success');
    }

    // Clean up the object URL
    setTimeout(() => URL.revokeObjectURL(url), 100);
  });
}

// Show status message
function showStatus(message, type = 'info') {
  statusMessage.textContent = message;

  // Reset styles
  statusMessage.className = '';

  // Apply style based on message type
  switch(type) {
    case 'error':
      statusMessage.style.color = 'var(--error-color)';
      break;
    case 'success':
      statusMessage.style.color = 'var(--success-color)';
      break;
    case 'warning':
      statusMessage.style.color = 'var(--warning-color)';
      break;
    default:
      statusMessage.style.color = 'var(--text-muted)';
  }

  // Auto-clear status after 3 seconds for success messages
  if (type === 'success') {
    setTimeout(() => {
      statusMessage.textContent = '';
    }, 3000);
  }
}

// Show or hide the spinner
function showSpinner(show) {
  spinner.style.display = show ? 'block' : 'none';
}
