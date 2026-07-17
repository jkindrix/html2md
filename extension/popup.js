// DOM Elements
const convertBtn = document.getElementById('convert-btn');
const settingsBtn = document.getElementById('settings-btn');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const conversionModeSelect = document.getElementById('conversion-mode');
const outputActionSelect = document.getElementById('output-action');
const resultContainer = document.getElementById('result-container');
const markdownResult = document.getElementById('markdown-result');
const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');
const statusMessage = document.getElementById('status-message');
const spinner = document.getElementById('spinner');
const saveSettingsBtn = document.getElementById('save-settings');
const resetDefaultsBtn = document.getElementById('reset-defaults');

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
  }
};

// Current settings - will be loaded from storage
let settings = {...defaultSettings};

const converter = new Html2MdConverter();
const settingsStore = new Html2MdSettingsStore(chrome.storage.sync);

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
  settingsStore.load(defaultSettings, loaded => {
    settings = loaded;
    applySettings();
  });
}

// Save settings to Chrome storage
function saveSettings() {
  settingsStore.save(settings, () => {
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

  converter.configure(settings);
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

  // Settings button opens the packaged settings tab.
  settingsBtn.addEventListener('click', () => {
    document.getElementById('settings-tab').click();
  });

  // Save settings button
  saveSettingsBtn.addEventListener('click', () => {
    updateSettingsFromForm();
    saveSettings();
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

  // Tab navigation with accessibility support
  const tabButtons = document.querySelectorAll('.tab-button');
  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      // Get the tab ID
      const tabId = button.getAttribute('data-tab');

      // Update all tab buttons (remove active state and aria-selected)
      document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
        btn.setAttribute('aria-selected', 'false');
        btn.tabIndex = -1;
      });

      // Update all tab panels (remove active state)
      document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
        pane.tabIndex = -1;
      });

      // Activate the selected tab button
      button.classList.add('active');
      button.setAttribute('aria-selected', 'true');
      button.tabIndex = 0;

      // Activate the corresponding tab panel
      const panel = document.getElementById(tabId);
      panel.classList.add('active');
      panel.tabIndex = 0;

      // Set focus to the panel if using keyboard
      if (window.keyboardNavigation) {
        panel.focus();
      }
    });

    // Handle keyboard navigation
    button.addEventListener('keydown', (e) => {
      // Set a flag to indicate keyboard navigation
      window.keyboardNavigation = true;

      // Left/right keys to navigate between tabs
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();

        const buttons = Array.from(tabButtons);
        const currentIndex = buttons.indexOf(button);
        let newIndex;

        if (e.key === 'ArrowRight') {
          newIndex = (currentIndex + 1) % buttons.length;
        } else {
          newIndex = (currentIndex - 1 + buttons.length) % buttons.length;
        }

        buttons[newIndex].click();
        buttons[newIndex].focus();
      }
    });
  });

  // Reset keyboard navigation flag on mouse use
  document.addEventListener('mousedown', () => {
    window.keyboardNavigation = false;
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

  converter.configure(settings);
}

// Handle the conversion process
function handleConversion() {
  const conversionMode = conversionModeSelect.value;
  const outputAction = outputActionSelect.value;

  showStatus('Converting...', 'processing');
  showSpinner(true);

  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];

    const extract = () => chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: extractPageContent,
      args: [conversionMode]
    }, (results) => {
      if (chrome.runtime.lastError) {
        showStatus('Error: ' + chrome.runtime.lastError.message, 'error');
        showSpinner(false);
        return;
      }

      const extractedContent = results[0].result;

      if (!extractedContent) {
        showStatus('Error: Could not extract content', 'error');
        showSpinner(false);
        return;
      }
      
      const htmlContent = Html2MdConversionUtils.normalizeExtractedHtml(extractedContent);

      // Convert HTML to Markdown
      const markdown = convertToMarkdown(htmlContent);

      // Handle the output based on user selection
      handleOutput(markdown, outputAction, tab.title);

      showStatus('Conversion complete', 'success');
      showSpinner(false);
    });

    if (conversionMode === 'article') {
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['readability.js']
      }, () => {
        if (chrome.runtime.lastError) {
          showStatus('Error: ' + chrome.runtime.lastError.message, 'error');
          showSpinner(false);
          return;
        }
        extract();
      });
    } else {
      extract();
    }
  });
}

// Extract content from the page based on mode
function extractPageContent(mode) {
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
      }
      break;
    case 'article':
      if (typeof Readability !== 'function') return '';
      const article = new Readability(document.cloneNode(true)).parse();
      content = article && article.content ? article.content : '';
      break;
  }

  return content;
}

// Convert HTML to Markdown using TurndownService
function convertToMarkdown(html) {
  return converter.convert(html);
}

// Handle the output based on selected action
function handleOutput(markdown, action, pageTitle) {
  switch(action) {
    case 'show':
      // Show in popup
      markdownResult.textContent = markdown;
      resultContainer.style.display = 'block';
      return Promise.resolve();
    case 'download':
      // Download as file
      return downloadMarkdown(markdown, pageTitle);
    case 'copy':
      // Copy to clipboard
      return navigator.clipboard.writeText(markdown).then(() => {
        showStatus('Copied to clipboard', 'success');
      }).catch(err => {
        showStatus('Failed to copy: ' + err, 'error');
        throw err;
      });
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

  return new Promise(resolve => {
    chrome.downloads.download({
      url: url,
      filename: filename,
      saveAs: false
    }, downloadId => {
      const error = chrome.runtime.lastError?.message || null;
      if (error) {
        showStatus('Error saving file: ' + error, 'error');
      } else {
        showStatus('File saved', 'success');
      }

      setTimeout(() => URL.revokeObjectURL(url), 1000);
      resolve({ downloadId, error });
    });
  });
}

/**
 * Show status message to the user
 * @param {string} message - Message to display
 * @param {string} type - Message type (info, success, warning, error)
 */
function showStatus(message, type = 'info') {
  statusMessage.textContent = message;

  // Reset styles
  statusMessage.className = '';
  statusMessage.style.color = '';

  // Add class based on message type
  statusMessage.classList.add(type);

  // Auto-clear status after some time for non-error messages
  if (type !== 'error') {
    const clearDelay = type === 'warning' ? 5000 : 3000;

    // Clear any existing timers
    if (window.statusTimer) {
      clearTimeout(window.statusTimer);
    }

    // Set new timer
    window.statusTimer = setTimeout(() => {
      statusMessage.textContent = '';
      statusMessage.className = '';
    }, clearDelay);
  }
}

// Show or hide the spinner
function showSpinner(show) {
  spinner.style.display = show ? 'block' : 'none';
}
