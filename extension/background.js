// Background script for HTML2MD extension

// Context menu setup
chrome.runtime.onInstalled.addListener(() => {
  // Create context menu items
  chrome.contextMenus.create({
    id: "convert-page",
    title: "Convert page to Markdown",
    contexts: ["page"]
  });

  chrome.contextMenus.create({
    id: "convert-selection",
    title: "Convert selection to Markdown",
    contexts: ["selection"]
  });

  chrome.contextMenus.create({
    id: "separator",
    type: "separator",
    contexts: ["page", "selection"]
  });

  chrome.contextMenus.create({
    id: "open-settings",
    title: "Open HTML2MD settings",
    contexts: ["page", "selection"]
  });
});

// Listen for keyboard shortcuts
chrome.commands.onCommand.addListener((command) => {
  if (command === "convert_selection") {
    // Handle converting selection
    convertWithOptions({ mode: "selection", output: "copy" });
  }
});

// Listen for context menu clicks
chrome.contextMenus.onClicked.addListener((info, tab) => {
  switch (info.menuItemId) {
    case "convert-page":
      convertWithOptions({ mode: "full-page", output: "download" }, tab);
      break;
    case "convert-selection":
      convertWithOptions({ mode: "selection", output: "copy" }, tab);
      break;
    case "open-settings":
      // Open the popup in a new tab for settings
      chrome.tabs.create({ url: chrome.runtime.getURL("popup.html?settings=true") });
      break;
  }
});

// Function to convert content with given options
function convertWithOptions(options, tab) {
  if (!tab) {
    // Get the active tab if not provided
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length > 0) {
        executeConversion(options, tabs[0]);
      }
    });
  } else {
    executeConversion(options, tab);
  }
}

// Execute the conversion
function executeConversion(options, tab) {
  // First load settings
  chrome.storage.sync.get('html2mdSettings', (data) => {
    const settings = data.html2mdSettings || {};
    const trimContent = settings.trim !== undefined ? settings.trim : true;

    // Inject script to extract content
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: extractPageContent,
      args: [options.mode, trimContent]
    }, (results) => {
      if (chrome.runtime.lastError || !results || !results[0]) {
        console.error("Error extracting content:", chrome.runtime.lastError);
        return;
      }

      const htmlContent = results[0].result;

      // Convert HTML to Markdown
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["turndown.js"]
      }, () => {
        chrome.scripting.executeScript({
          target: { tabId: tab.id },
          function: convertToMarkdown,
          args: [htmlContent, trimContent, settings]
        }, (conversionResults) => {
          if (chrome.runtime.lastError || !conversionResults || !conversionResults[0]) {
            console.error("Error converting content:", chrome.runtime.lastError);
            return;
          }

          const markdown = conversionResults[0].result;

          // Handle the output based on option
          handleOutput(markdown, options.output, tab);
        });
      });
    });
  });
}

// Extract content from the page based on mode (injected into the page)
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

// Convert HTML to Markdown (injected into the page)
function convertToMarkdown(html, trim, settings) {
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

  // Initialize TurndownService with settings
  const turndownOptions = {
    headingStyle: settings?.markdownOptions?.headingStyle || 'atx',
    bulletListMarker: settings?.markdownOptions?.bulletMarker || '-',
    linkStyle: settings?.markdownOptions?.linkStyle || 'inline',
    codeBlockStyle: settings?.contentOptions?.codeBlocks ? 'fenced' : 'indented'
  };

  const turndownService = new TurndownService(turndownOptions);

  // Configure Turndown based on settings
  if (settings?.contentOptions?.preserveImages === false) {
    turndownService.remove('img');
  }

  return turndownService.turndown(html);
}

// Handle the output
function handleOutput(markdown, outputType, tab) {
  switch (outputType) {
    case "copy":
      // Copy to clipboard using the content script
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        function: (text) => {
          navigator.clipboard.writeText(text).then(() => {
            // Show a notification
            const notification = document.createElement("div");
            notification.textContent = "Markdown copied to clipboard!";
            notification.style.cssText = `
              position: fixed;
              top: 20px;
              left: 50%;
              transform: translateX(-50%);
              background: #4caf50;
              color: white;
              padding: 10px 20px;
              border-radius: 5px;
              box-shadow: 0 2px 10px rgba(0,0,0,0.2);
              z-index: 9999;
              font-family: system-ui, sans-serif;
            `;
            document.body.appendChild(notification);

            // Remove after 3 seconds
            setTimeout(() => {
              notification.remove();
            }, 3000);
          });
        },
        args: [markdown]
      });
      break;

    case "download":
      // Clean the filename
      let filename = tab.title
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
        // Clean up the object URL
        setTimeout(() => URL.revokeObjectURL(url), 100);
      });
      break;
  }
}
