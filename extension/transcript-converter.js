/**
 * ChatGPT Transcript Converter
 * 
 * A specialized converter for ChatGPT conversations that produces
 * a standardized, semantic transcript format with proper metadata
 * and consistent structure.
 */

class TranscriptConverter {
  /**
   * Convert ChatGPT HTML to a standardized transcript format
   * @param {string} html - Raw HTML from ChatGPT
   * @returns {string} - Formatted Markdown transcript
   */
  static convert(html) {
    // First check if this is already in our format but broken
    if (html.includes('title: "ChatGPT Conversation Transcript"') && 
        html.includes('format: "transcript-v1.0"') &&
        html.includes('# Conversation Transcript')) {
      console.log('Found existing transcript format, cleaning up...');
      return this.cleanupExistingTranscript(html);
    }

    // Set up result variables
    const messages = [];
    let pageTitle = "ChatGPT Conversation";
    
    try {
      // Create a safe DOM element to parse HTML
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = html;
      
      // Try to extract page title
      const titleElement = tempDiv.querySelector('title');
      if (titleElement && titleElement.textContent) {
        pageTitle = titleElement.textContent;
      }
      
      // Remove UI elements we don't want
      this.removeUIElements(tempDiv);
      
      // Extract messages
      this.extractMessages(tempDiv, messages);
      
      // If no messages were found, try raw text extraction
      if (messages.length === 0) {
        console.log('No messages found in DOM structure, trying raw text extraction');
        
        // Log available elements for debugging
        console.log('Available elements in DOM:');
        const articles = tempDiv.querySelectorAll('article');
        console.log(`- Found ${articles.length} article elements`);
        
        const dataTest = tempDiv.querySelectorAll('[data-testid]');
        console.log(`- Found ${dataTest.length} data-testid elements`);
        
        const headings = tempDiv.querySelectorAll('h1, h2, h3, h4, h5, h6');
        console.log(`- Found ${headings.length} heading elements`);
        
        const paragraphs = tempDiv.querySelectorAll('p');
        console.log(`- Found ${paragraphs.length} paragraph elements`);
        
        const divs = tempDiv.querySelectorAll('div');
        console.log(`- Found ${divs.length} div elements`);
        
        this.extractFromRawText(html, messages);
      }
      
      // If still no messages, try a simple extraction method
      if (messages.length === 0) {
        console.log('Raw text extraction failed, trying simple content extraction');
        this.extractSimpleContent(tempDiv, messages);
      }
      
      // If still no messages, show sample HTML and return a placeholder
      if (messages.length === 0) {
        console.error('All extraction methods failed. HTML preview:', html.substring(0, 500));
        
        // Log more details to console
        console.log('HTML Structure Sample:');
        if (tempDiv.innerHTML.length > 0) {
          // Print a sample of the DOM structure for debugging
          const sampleNodes = Array.from(tempDiv.children).slice(0, 3);
          sampleNodes.forEach((node, index) => {
            console.log(`Node ${index + 1} tagName:`, node.tagName);
            console.log(`Node ${index + 1} classList:`, node.classList?.value || 'none');
            console.log(`Node ${index + 1} attributes:`, Array.from(node.attributes || []).map(attr => `${attr.name}="${attr.value}"`).join(', '));
            console.log(`Node ${index + 1} childNodes:`, node.childNodes.length);
          });
        }
        
        // Show example of turns - this helps debug the ChatGPT structure
        console.log('Here are examples of turns:', tempDiv.innerHTML.substring(0, 1000));
        
        return this.createPlaceholderTranscript();
      }
      
      console.log('Successfully extracted', messages.length, 'messages');
      
      // Generate the final transcript
      return this.generateTranscript(messages, pageTitle);
      
    } catch (error) {
      console.error('Error converting HTML to transcript:', error);
      console.error('HTML preview:', html.substring(0, 500));
      return this.createPlaceholderTranscript();
    }
  }
  
  /**
   * Clean up a transcript that's already in our format but broken
   * @param {string} html - HTML or Markdown content
   * @returns {string} - Cleaned up transcript
   */
  static cleanupExistingTranscript(html) {
    // Extract the messages from the existing transcript
    const messages = [];
    
    try {
      // Create a temporary div for parsing
      const tempDiv = document.createElement('div');
      
      // Try to determine if it's HTML or just markdown text
      if (html.includes('<!DOCTYPE html>') || html.includes('<html') || html.includes('<body')) {
        tempDiv.innerHTML = html;
        html = tempDiv.textContent || html;
      }
      
      // Now we should have plain text
      let plainText = html;
      
      // Extract the frontmatter
      let frontmatter = '';
      const frontmatterMatch = plainText.match(/---\s*([\s\S]*?)---/);
      if (frontmatterMatch) {
        frontmatter = frontmatterMatch[0];
        plainText = plainText.replace(frontmatterMatch[0], '');
      }
      
      // Clean up line breaks and spaces
      plainText = plainText.replace(/\r\n/g, '\n')
                           .replace(/\n{3,}/g, '\n\n')
                           .trim();
      
      console.log('Cleaned plaintext preview:', plainText.substring(0, 200));
      
      // Look for message exchanges
      const exchangeMatches = plainText.match(/## Message Exchange \d+/g) || [];
      if (exchangeMatches.length > 0) {
        const exchanges = plainText.split(/## Message Exchange \d+/);
        
        // Skip the first part (it usually contains the title)
        for (let i = 1; i < exchanges.length; i++) {
          const exchange = exchanges[i].trim();
          
          // Find user and assistant messages
          const userMatch = exchange.match(/\*\*User\*\*:\s*([\s\S]*?)(?=\*\*Assistant\*\*:|$)/);
          const assistantMatch = exchange.match(/\*\*Assistant\*\*:\s*([\s\S]*?)(?=\*\*User\*\*:|$)/);
          
          if (userMatch) {
            messages.push({
              role: 'user',
              content: userMatch[1].trim()
            });
          }
          
          if (assistantMatch) {
            messages.push({
              role: 'assistant',
              content: assistantMatch[1].trim()
            });
          }
        }
      } else {
        // Try a different approach - just look for User/Assistant markers
        const userMarkers = plainText.match(/\*\*User\*\*:/g) || [];
        const assistantMarkers = plainText.match(/\*\*Assistant\*\*:/g) || [];
        
        if (userMarkers.length > 0 || assistantMarkers.length > 0) {
          // Split by the markers and extract content
          const parts = plainText.split(/\*\*(?:User|Assistant)\*\*:/);
          
          // Skip the first part (it's before any markers)
          for (let i = 1; i < parts.length; i++) {
            const content = parts[i].trim();
            const role = plainText.indexOf(`**User**:${parts[i]}`) > -1 ? 'user' : 'assistant';
            
            if (content.length > 0) {
              messages.push({
                role,
                content
              });
            }
          }
        }
      }
      
      console.log('Extracted', messages.length, 'messages from existing transcript');
      
      // If we found messages, generate a new transcript
      if (messages.length > 0) {
        return this.generateTranscript(messages, "ChatGPT Conversation");
      }
      
      // Fallback: just remove duplicate frontmatter and clean up
      console.log('Falling back to basic cleanup');
      return this.basicCleanup(plainText);
    
    } catch (error) {
      console.error('Error in cleanupExistingTranscript:', error);
      
      // Just return a cleaned version of the text
      return this.basicCleanup(html);
    }
  }
  
  /**
   * Basic cleanup for broken markdown
   * @param {string} text - Text to clean up
   * @returns {string} - Cleaned text
   */
  static basicCleanup(text) {
    // Extract the first frontmatter if present
    const frontmatterRegex = /---\s*title.*?---\s*/gs;
    const frontmatters = text.match(frontmatterRegex) || [];
    
    if (frontmatters.length > 0) {
      // Extract the first frontmatter
      const firstFrontmatter = frontmatters[0];
      
      // Remove all frontmatter instances
      text = text.replace(frontmatterRegex, '');
      
      // Add back only the first frontmatter
      text = firstFrontmatter + text;
    } else {
      // Add frontmatter if none exists
      const date = new Date().toISOString().split('T')[0];
      text = `---
title: "ChatGPT Conversation Transcript"
date: "${date}"
format: "transcript-v1.0"
---

` + text;
    }
    
    // Ensure only one main title
    const mainTitleRegex = /# Conversation Transcript/g;
    const mainTitles = text.match(mainTitleRegex) || [];
    
    if (mainTitles.length === 0) {
      // Add a main title if none exists
      text = text.trim() + '\n\n# Conversation Transcript\n\n';
    } else if (mainTitles.length > 1) {
      // Keep only the first main title
      let firstIndex = text.indexOf('# Conversation Transcript');
      text = text.substring(0, firstIndex + '# Conversation Transcript'.length) + 
             text.substring(firstIndex + '# Conversation Transcript'.length).replace(mainTitleRegex, '');
    }
    
    // Fix code blocks
    text = this.fixCodeBlocks(text);
    
    return text;
  }
  
  /**
   * Fix code blocks in markdown
   * @param {string} markdown - Markdown text
   * @returns {string} - Fixed markdown
   */
  static fixCodeBlocks(markdown) {
    // Fix common code block issues
    
    // 1. Replace single backticks with triple backticks for multi-line code
    let fixed = markdown;
    
    // Find code blocks with single backticks that contain newlines (they should be triple backticks)
    const singleBacktickRegex = /`([^`]+?\n[^`]+?)`/g;
    fixed = fixed.replace(singleBacktickRegex, (match, content) => {
      // Check if this spans multiple lines
      const lineCount = content.split('\n').length;
      if (lineCount > 2) {
        // Detect if there's likely a language identifier on the first line
        const firstLine = content.split('\n')[0].trim().toLowerCase();
        const isLanguageIdentifier = /^(javascript|js|typescript|ts|python|py|java|cpp|csharp|c#|ruby|rb|php|go|golang|rust|html|css|json|yaml|yml|bash|shell|sh|sql|markdown|md)$/i.test(firstLine);
        
        if (isLanguageIdentifier) {
          // If the first line is a language identifier, move it to the code fence
          const restOfContent = content.split('\n').slice(1).join('\n').trim();
          return '```' + firstLine + '\n' + restOfContent + '\n```';
        } else {
          return '```\n' + content + '\n```';
        }
      }
      return match; // Keep as is if it's just a short span
    });
    
    // 2. Fix language identifiers
    // Common pattern in ChatGPT: language name appears before code block
    const languageIdentifiers = [
      'javascript', 'js', 'typescript', 'ts', 'python', 'py', 'java', 
      'cpp', 'c#', 'csharp', 'ruby', 'rb', 'php', 'go', 'golang', 
      'rust', 'html', 'css', 'json', 'yaml', 'yml', 'bash', 'shell', 'sh', 
      'sql', 'markdown', 'md', 'text', 'txt', 'plaintext', 'xml'
    ];
    
    // Replace stand-alone language identifiers followed by code blocks
    for (const lang of languageIdentifiers) {
      // Match the pattern where a language identifier is on its own line before a code block
      const pattern = new RegExp(`\\b${lang}\\s*\n+\\s*\`\`\`\\s*\n`, 'gi');
      fixed = fixed.replace(pattern, '```' + lang.toLowerCase() + '\n');
      
      // More aggressive pattern: language at end of a line followed by code block
      const patternAtEndOfLine = new RegExp(`\\b${lang}:\\s*\n+\\s*\`\`\`\\s*\n`, 'gi');
      fixed = fixed.replace(patternAtEndOfLine, '```' + lang.toLowerCase() + '\n');
      
      // Handle "In {language}:" pattern
      const inLangPattern = new RegExp(`In\\s+${lang}:\\s*\n+\\s*\`\`\`\\s*\n`, 'gi');
      fixed = fixed.replace(inLangPattern, '```' + lang.toLowerCase() + '\n');
    }
    
    // 3. Fix case where language is inside the code block on the first line
    // Common in ChatGPT: language is mentioned in the first line of the code block
    fixed = fixed.replace(/```\s*\n(javascript|js|typescript|ts|python|py|java|cpp|csharp|c#|ruby|rb|php|go|golang|rust|html|css|json|yaml|yml|bash|shell|sh|sql|markdown|md)[\s:]*\n/gi, (match, lang) => {
      return '```' + lang.toLowerCase() + '\n';
    });
    
    // 4. Fix nested backticks
    fixed = fixed.replace(/``\s*```/g, '```');
    fixed = fixed.replace(/```\s*``/g, '```');
    fixed = fixed.replace(/````+/g, '```'); // Fix excessive backticks (4+)
    
    // 5. Fix broken or incomplete code blocks
    fixed = fixed.replace(/```(\w*)\s*\n+/g, '```$1\n');
    fixed = fixed.replace(/\n+\s*```/g, '\n```');
    
    // 6. Fix mixed spacing in language identifiers
    fixed = fixed.replace(/```\s+(\w+)/g, '```$1');
    
    // 7. Fix code blocks that don't start and end with newlines
    fixed = fixed.replace(/([^\n])```(\w*)/g, '$1\n```$2');
    fixed = fixed.replace(/```([^\n])/g, '```\n$1');
    
    // 8. Fix code blocks with no closing fence before another section starts
    const sectionStarts = ['## Message Exchange', '**User**:', '**Assistant**:'];
    for (const sectionStart of sectionStarts) {
      const pattern = new RegExp(`\`\`\`(\\w*)\\n([\\s\\S]*?)(?=\\n${sectionStart})`, 'g');
      fixed = fixed.replace(pattern, (match, lang, content) => {
        if (!match.includes('\n```')) {
          return '```' + lang + '\n' + content + '\n```\n\n';
        }
        return match;
      });
    }
    
    // 9. Ensure each opening code fence has a matching closing fence
    const openCodeBlocks = fixed.match(/```\w*\n/g) || [];
    const closeCodeBlocks = fixed.match(/\n```/g) || [];
    
    if (openCodeBlocks.length > closeCodeBlocks.length) {
      // Add missing closing fences at the end of paragraphs
      const splitByOpen = fixed.split(/```\w*\n/);
      let result = splitByOpen[0];
      
      for (let i = 1; i < splitByOpen.length; i++) {
        const part = splitByOpen[i];
        // Add opening fence
        result += openCodeBlocks[i-1];
        
        // Check if this part already has a closing fence
        if (part.includes('\n```')) {
          result += part;
        } else {
          // Find a good place to insert the closing fence
          const paragraphBreak = part.search(/\n\n/);
          if (paragraphBreak > 0) {
            result += part.substring(0, paragraphBreak) + '\n```' + part.substring(paragraphBreak);
          } else {
            result += part + '\n```';
          }
        }
      }
      fixed = result;
    }
    
    // 10. Make code blocks more readable by adding empty lines around them
    fixed = fixed.replace(/([^\n])(\n```)/g, '$1\n$2');
    fixed = fixed.replace(/(```\n)([^\n])/g, '$1\n$2');
    
    // 11. Final pass to fix any remaining issues
    // Remove empty code blocks
    fixed = fixed.replace(/```\w*\s*\n\s*```/g, '');
    
    // Fix duplicate language identifiers
    fixed = fixed.replace(/```(\w+)\n\1\n/gi, '```$1\n');
    
    return fixed;
  }
  
  /**
   * Remove unwanted UI elements from the document
   * @param {Document} doc - HTML document
   */
  static removeUIElements(doc) {
    // List of selectors for UI elements to remove
    const selectorsToRemove = [
      // Basic HTML elements
      'script', 'style', 'svg', 'head', 'nav', 'footer', 'header', 'aside',
      'title', 'meta', 'link', 'noscript',
      
      // Interactive elements
      'button', 'input', 'select', 'textarea', 'form', 'menu', 'dialog',
      
      // Common UI components
      '.copy-button', '.edit-button', '.regenerate-button', '.share-button',
      '.sidebar', '.search-box', '.user-menu', '.login-container',
      '.toast', '.modal', '.disclaimer', '.cookie-banner', '.alert',
      '.buttons', '.actionbar', '.input-panel', '.toolbar', '.navigation',
      '.pagination', '.search-results', '.menu-dropdown', '.settings',
      '.skip-link', '.chat-history', '.main-header', '.main-footer',
      
      // ARIA roles
      '[role="banner"]', '[role="navigation"]', '[role="complementary"]',
      '[role="dialog"]', '[role="search"]', '[role="toolbar"]', 
      '[role="menubar"]', '[role="menu"]', '[role="tab"]', '[role="tabpanel"]',
      '[role="alert"]', '[role="status"]', '[role="button"]',
      
      // ChatGPT specific UI elements
      '.flex-shrink-0', '.self-end', '.text-gray-400', '.text-gray-600',
      '.text-gray-500', '.text-xs', '.text-sm', '.py-2', '.px-3',
      '[data-testid="search-box"]', '[data-testid="send-button"]',
      '[data-testid="model-switcher"]', '[data-testid="chat-sidebar"]',
      '[aria-label="Menu"]', '[data-testid="copy-button"]',
      '[data-state="closed"]', '[data-state="open"]', '[data-message-id]',
      '.markdown-render-content', '.w-full', '.text-base',
      '.text-token-text-secondary', '.text-token-text-tertiary',
      'h1.text-4xl', '.flex-col', '.h-full', '.relative', '.absolute'
    ];
    
    // Remove elements matching selectors
    for (const selector of selectorsToRemove) {
      try {
        const elements = doc.querySelectorAll(selector);
        for (const element of elements) {
          element.parentNode?.removeChild(element);
        }
      } catch (e) {
        // Ignore invalid selectors
      }
    }
    
    // Remove elements with specific text content patterns
    const uiTextPatterns = [
      /skip to content/i, /open sidebar/i, /chat history/i, 
      /search/i, /deep research/i, /create image/i, /share/i,
      /answer in chat/i, /saved memory/i, /undefined/i,
      /^openai$/i, /^chatgpt$/i, /^gpt-4$/i, /^gpt-3\.5$/i,
      /^Model:.*/i, /^ChatGPT.*/i, /^GPT-4o.*/i,
      /can make mistakes/i, /workspace data/i, /train its models/i,
      /Justin('s)? Workspace/i, /Answer in chat/i
    ];
    
    // Find and remove elements with UI text patterns
    try {
      // First remove heading elements that match UI patterns
      const headings = doc.querySelectorAll('h1, h2, h3, h4, h5, h6');
      for (const heading of headings) {
        const text = heading.textContent.trim();
        if (text === 'Chat history' || /^ChatGPT/.test(text) || text === 'Skip to content') {
          heading.parentNode?.removeChild(heading);
        }
      }
      
      // Then check all elements
      const allElements = doc.querySelectorAll('*');
      for (const element of allElements) {
        // Skip elements that are likely part of the actual content
        if (element.tagName === 'PRE' || element.tagName === 'CODE' || 
            element.classList.contains('markdown') || 
            element.classList.contains('message-content')) {
          continue;
        }
        
        const text = element.textContent.trim();
        // If the element contains text that matches UI patterns
        if (uiTextPatterns.some(pattern => pattern.test(text))) {
          try {
            // If it's a small text node that exactly matches the pattern
            // or if it's a small element, remove it completely
            if (text.length < 50 || element.children.length === 0) {
              element.parentNode?.removeChild(element);
            } else {
              // For larger elements, try to just remove the UI text
              for (const pattern of uiTextPatterns) {
                if (pattern.test(text)) {
                  try {
                    element.innerHTML = element.innerHTML.replace(pattern, '');
                  } catch (innerErr) {
                    // If innerHTML manipulation fails, try with textContent
                    try {
                      element.textContent = element.textContent.replace(pattern, '');
                    } catch (textErr) {
                      console.warn('Failed to clean element text:', textErr);
                    }
                  }
                }
              }
            }
          } catch (e) {
            console.warn('Error cleaning UI element:', e.message);
          }
        }
      }
      
      // Also clean text nodes directly
      const walk = document.createTreeWalker(doc, NodeFilter.SHOW_TEXT);
      const nodesToRemove = [];
      while (walk.nextNode()) {
        const node = walk.currentNode;
        const text = node.textContent.trim();
        
        if (text && uiTextPatterns.some(pattern => pattern.test(text))) {
          nodesToRemove.push(node);
        }
      }
      
      // Remove gathered text nodes
      for (const node of nodesToRemove) {
        try {
          node.parentNode?.removeChild(node);
        } catch (e) {
          // Ignore errors
        }
      }
    } catch (e) {
      console.error('Error removing UI text elements:', e);
    }
    
    // Remove any remaining nodes that contain specific UI strings
    try {
      const uiStrings = [
        'Skip to content', 'Chat history', 'Open sidebar', 'Share', 'Search',
        'Deep research', 'Saved memory full', 'undefined', 'Answer in chat instead'
      ];
      
      // Create an HTML string to search and replace
      let htmlContent = doc.innerHTML;
      uiStrings.forEach(str => {
        htmlContent = htmlContent.replace(new RegExp(str, 'g'), '');
      });
      
      // Set the updated HTML content
      doc.innerHTML = htmlContent;
    } catch (e) {
      console.error('Error removing UI strings:', e);
    }
    
    // Clean up leftover UI classes that might affect the rendering
    try {
      const allElements = doc.querySelectorAll('*');
      allElements.forEach(el => {
        if (el.className && typeof el.className === 'string') {
          // Remove classes that are likely UI-related
          const uiClassPatterns = [
            /^flex-/, /^text-/, /^bg-/, /^p-/, /^m-/, /^w-/, /^h-/,
            /button/, /icon/, /avatar/, /menu/, /header/, /footer/, /sidebar/,
            /chat/, /search/, /panel/, /dialog/, /modal/, /toast/
          ];
          
          if (uiClassPatterns.some(pattern => pattern.test(el.className))) {
            try {
              // Only remove the UI-related classes, not all classes
              const classes = el.className.split(' ');
              const filteredClasses = classes.filter(cls => 
                !uiClassPatterns.some(pattern => pattern.test(cls))
              );
              el.className = filteredClasses.join(' ');
            } catch (e) {
              // Ignore errors
            }
          }
        }
      });
    } catch (e) {
      console.error('Error cleaning UI classes:', e);
    }
  }
  
  /**
   * Extract messages from document
   * @param {Document} doc - HTML document
   * @param {Array} messages - Array to store extracted messages
   */
  static extractMessages(doc, messages) {
    // Try different message extraction strategies
    
    // Strategy 0: Latest ChatGPT structure (2025 version)
    if (this.extractLatestChatGPTFormat(doc, messages)) {
      return;
    }
    
    // Strategy 1: Modern ChatGPT structure
    if (this.extractMessagesModernChatGPT(doc, messages)) {
      return;
    }
    
    // Strategy 2: Legacy message structure
    if (this.extractMessagesLegacyFormat(doc, messages)) {
      return;
    }
    
    // Strategy 3: Generic conversation format
    this.extractMessagesGenericFormat(doc, messages);
  }
  
  /**
   * Extract messages from the latest ChatGPT DOM structure (2025)
   * @param {Document} doc - HTML document
   * @param {Array} messages - Array to store extracted messages
   * @returns {boolean} - True if messages were found
   */
  static extractLatestChatGPTFormat(doc, messages) {
    // Look specifically for the 2025 ChatGPT DOM structure
    // which uses article elements with specific attributes
    const turns = doc.querySelectorAll('article[data-testid^="conversation-turn-"]');
    
    if (turns.length === 0) {
      console.log('No 2025 ChatGPT turns found');
      return false;
    }
    
    console.log('Found 2025 ChatGPT structure with', turns.length, 'turns');
    
    let messageCount = 0;
    
    for (const turn of turns) {
      // Determine role based on the sr-only heading
      let role = 'assistant';
      const srOnlyHeading = turn.querySelector('h5.sr-only, h6.sr-only');
      
      if (srOnlyHeading) {
        const headingText = srOnlyHeading.textContent;
        if (headingText.includes('You said') || headingText.includes('User:')) {
          role = 'user';
        }
      }
      
      // For users, look for div with whitespace-pre-wrap class
      let contentElement = null;
      
      if (role === 'user') {
        contentElement = turn.querySelector('.whitespace-pre-wrap');
      } else {
        // For assistant, look for markdown or prose
        contentElement = turn.querySelector('.markdown.prose') || turn.querySelector('.prose') || turn.querySelector('.whitespace-pre-wrap');
      }
      
      // If we still don't have content, try a more general approach
      if (!contentElement || !contentElement.textContent.trim()) {
        // Look for any div with substantial content
        const allDivs = turn.querySelectorAll('div');
        for (const div of allDivs) {
          if (div.textContent.trim().length > 50) {
            contentElement = div;
            break;
          }
        }
      }
      
      // Skip if we couldn't find content
      if (!contentElement || !contentElement.textContent.trim()) {
        continue;
      }
      
      // Process content
      const content = this.processMessageContent(contentElement);
      
      // Only add if we got meaningful content
      if (content && content.trim().length > 10) {
        messages.push({
          role,
          content
        });
        messageCount++;
        console.log(`Added 2025 ${role} message with ${content.length} chars`);
      }
    }
    
    return messageCount > 0;
  }
  
  /**
   * Extract messages from modern ChatGPT structure
   * @param {Document} doc - HTML document
   * @param {Array} messages - Array to store extracted messages
   * @returns {boolean} - True if messages were found
   */
  static extractMessagesModernChatGPT(doc, messages) {
    // Look for conversation turns - handling the latest ChatGPT DOM structure
    const turns = doc.querySelectorAll('[data-testid^="conversation-turn-"], [data-message-author-role], article');
    
    if (turns.length === 0) {
      return false;
    }
    
    console.log('Found modern ChatGPT structure with', turns.length, 'turns');
    
    for (const turn of turns) {
      // Determine role
      let isUser = false;
      
      // Check various ways to identify user messages
      if (turn.getAttribute('data-message-author-role') === 'user') {
        isUser = true;
      } else if (turn.querySelector('[data-message-author-role="user"]')) {
        isUser = true;
      } else if (turn.querySelector('.min-h-8[data-message-author-role="user"]')) {
        isUser = true;
      } else if (turn.querySelector('h5.sr-only') && turn.querySelector('h5.sr-only').textContent.includes('You said')) {
        isUser = true;
      }
      
      const role = isUser ? 'user' : 'assistant';
      
      // Extract content - try multiple selectors to find the content
      const contentSelectors = [
        '.markdown', 
        '.whitespace-pre-wrap',
        '.min-h-8[data-message-author-role] .whitespace-pre-wrap',
        '.min-h-8[data-message-author-role] .markdown',
        '.min-h-8 .prose',
        '[data-message-author-role] .markdown',
        '[data-message-author-role] div div',
        '.text-message .relative',
        '.text-base'
      ];
      
      let contentElement = null;
      
      // Try each selector until we find content
      for (const selector of contentSelectors) {
        const el = turn.querySelector(selector);
        if (el && el.textContent && el.textContent.trim().length > 10) {
          contentElement = el;
          break;
        }
      }
      
      // If we still didn't find it, use the turn itself
      if (!contentElement) {
        contentElement = turn;
      }
      
      // Skip empty messages
      if (!contentElement.textContent.trim()) continue;
      
      // Process content
      const content = this.processMessageContent(contentElement);
      
      // Only add if we got meaningful content (longer than a few chars)
      if (content && content.trim().length > 5) {
        messages.push({
          role,
          content
        });
        console.log(`Added ${role} message with ${content.length} chars`);
      }
    }
    
    return messages.length > 0;
  }
  
  /**
   * Extract messages from legacy ChatGPT format
   * @param {Document} doc - HTML document
   * @param {Array} messages - Array to store extracted messages
   * @returns {boolean} - True if messages were found
   */
  static extractMessagesLegacyFormat(doc, messages) {
    // Look for chat message classes and common message patterns
    const chatMessages = doc.querySelectorAll(
      '.chat-message, .user-message, .assistant-message, ' + 
      '.message, .user, .assistant, .text-message, ' + 
      '[role="user"], [role="assistant"], ' +
      '.min-h-8, .relative.flex.w-full'
    );
    
    if (chatMessages.length === 0) {
      return false;
    }
    
    console.log('Found legacy chat message structure with', chatMessages.length, 'messages');
    
    for (const msg of chatMessages) {
      // Determine role
      let isUser = false;
      
      // Check various user indicators
      if (msg.classList.contains('user-message') || 
          msg.classList.contains('user') || 
          msg.querySelector('.user') ||
          msg.getAttribute('role') === 'user' ||
          msg.getAttribute('data-message-author-role') === 'user' ||
          msg.querySelector('[data-message-author-role="user"]')) {
        isUser = true;
      }
      
      // Look for "You:" or "User:" patterns in the text
      const msgText = msg.textContent.trim();
      if (msgText.startsWith('You:') || msgText.startsWith('User:') || 
          msg.querySelector('h5.sr-only, h6.sr-only')?.textContent.includes('You said')) {
        isUser = true;
      }
      
      const role = isUser ? 'user' : 'assistant';
      
      // Try multiple content selectors
      const contentSelectors = [
        '.message-content', 
        '.content',
        '.markdown',
        '.prose',
        '.whitespace-pre-wrap',
        'p',
        '.text-message',
        '[data-message-author-role] div div'
      ];
      
      let contentElement = null;
      
      // Try each selector
      for (const selector of contentSelectors) {
        const el = msg.querySelector(selector);
        if (el && el.textContent && el.textContent.trim().length > 5) {
          contentElement = el;
          break;
        }
      }
      
      // If no specific content element found, use the message itself
      if (!contentElement) {
        contentElement = msg;
      }
      
      // Skip empty messages
      if (!contentElement.textContent.trim()) continue;
      
      // Process content
      const content = this.processMessageContent(contentElement);
      
      // Only add if content is meaningful (more than a few chars)
      if (content && content.trim().length > 5) {
        messages.push({
          role,
          content
        });
        console.log(`Added legacy ${role} message with ${content.length} chars`);
      }
    }
    
    return messages.length > 0;
  }
  
  /**
   * Extract messages from generic conversation format
   * @param {Document} doc - HTML document
   * @param {Array} messages - Array to store extracted messages
   */
  static extractMessagesGenericFormat(doc, messages) {
    // Look for header markers and patterns
    
    // Common patterns for user/assistant headers
    const userPatterns = [
      /You said:/i, /User:/i, /Human:/i, /User\s*\d+/i,
      /Your message/i, /You:/i, /User input/i
    ];
    
    const assistantPatterns = [
      /ChatGPT said:/i, /GPT-\d+:/i, /Assistant:/i, /AI:/i, 
      /Assistant\s*\d+/i, /ChatGPT:/i, /Response:/i
    ];
    
    // Find all headings and paragraphs
    const elements = doc.querySelectorAll('h1, h2, h3, h4, h5, h6, p, div');
    
    let currentRole = null;
    let currentContent = [];
    
    for (const el of elements) {
      const text = el.textContent.trim();
      
      // Skip empty elements
      if (!text) continue;
      
      // Check if this is a user header
      const isUserHeader = userPatterns.some(pattern => pattern.test(text));
      
      // Check if this is an assistant header
      const isAssistantHeader = assistantPatterns.some(pattern => pattern.test(text));
      
      if (isUserHeader) {
        // Save previous message if any
        if (currentRole && currentContent.length > 0) {
          messages.push({
            role: currentRole,
            content: this.processElements(currentContent)
          });
          currentContent = [];
        }
        
        // Start a new user message
        currentRole = 'user';
        
      } else if (isAssistantHeader) {
        // Save previous message if any
        if (currentRole && currentContent.length > 0) {
          messages.push({
            role: currentRole,
            content: this.processElements(currentContent)
          });
          currentContent = [];
        }
        
        // Start a new assistant message
        currentRole = 'assistant';
        
      } else if (currentRole) {
        // Add this element to the current message
        currentContent.push(el);
      } else if (text.length > 20) {
        // If no role yet but substantial content, assume it's the user
        currentRole = 'user';
        currentContent.push(el);
      }
    }
    
    // Save the final message
    if (currentRole && currentContent.length > 0) {
      messages.push({
        role: currentRole,
        content: this.processElements(currentContent)
      });
    }
    
    // If we couldn't extract anything, try one more approach - look for alternating paragraphs
    if (messages.length === 0) {
      this.extractAlternatingMessages(doc, messages);
    }
  }
  
  /**
   * Extract messages assuming alternating user/assistant messages
   * @param {Document} doc - HTML document
   * @param {Array} messages - Array to store extracted messages
   */
  static extractAlternatingMessages(doc, messages) {
    // Get all paragraphs and content divs
    const paragraphs = Array.from(doc.querySelectorAll('p, div')).filter(el => {
      // Skip elements that are likely UI
      return el.textContent.trim().length > 10 && 
             !el.querySelector('button, input, select') &&
             !el.classList.contains('sidebar') &&
             !el.classList.contains('header') &&
             !el.classList.contains('footer');
    });
    
    if (paragraphs.length === 0) {
      return;
    }
    
    console.log('Trying alternating message extraction with', paragraphs.length, 'paragraphs');
    
    // Assume alternating user/assistant messages
    let role = 'user'; // Start with user
    let currentContent = [];
    let messageCount = 0;
    
    for (const paragraph of paragraphs) {
      const text = paragraph.textContent.trim();
      
      // Skip very short or empty paragraphs
      if (text.length < 5) continue;
      
      // Skip obvious UI elements
      if (text.match(/OpenAI|ChatGPT|4o|GPT-4o|Deep research|Create image|Share|Search|sidebar/i)) {
        continue;
      }
      
      // If this is a large paragraph after accumulating some content, start a new message
      if (currentContent.length > 0 && text.length > 100) {
        messages.push({
          role,
          content: this.processElements(currentContent)
        });
        currentContent = [];
        role = role === 'user' ? 'assistant' : 'user';
        messageCount++;
      }
      
      currentContent.push(paragraph);
    }
    
    // Add the final message
    if (currentContent.length > 0) {
      messages.push({
        role,
        content: this.processElements(currentContent)
      });
      messageCount++;
    }
    
    console.log('Extracted', messageCount, 'messages using alternating approach');
  }
  
  /**
   * Process array of elements into content
   * @param {Array} elements - Array of DOM elements
   * @returns {string} - Processed content
   */
  static processElements(elements) {
    if (elements.length === 0) {
      return '';
    }
    
    // Create a temporary container
    const container = document.createElement('div');
    
    // Add all elements to the container
    for (const el of elements) {
      container.appendChild(el.cloneNode(true));
    }
    
    // Process the container
    return this.processMessageContent(container);
  }
  
  /**
   * Extract from raw text when DOM structure fails
   * @param {string} html - Raw HTML text
   * @param {Array} messages - Array to store messages
   */
  static extractFromRawText(html, messages) {
    // Convert HTML to plain text
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    const text = tempDiv.textContent;
    
    // Common patterns for user/assistant headers
    const userHeaderRegex = /(?:You said:|User:|Human:|User\s*\d+:|You:|Your message:)/i;
    const assistantHeaderRegex = /(?:ChatGPT said:|GPT-\d+:|Assistant:|AI:|Assistant\s*\d+:|ChatGPT:|Response:)/i;
    
    // Split text into paragraphs
    const paragraphs = text.split(/\n{2,}/).map(p => p.trim()).filter(p => p);
    
    let currentRole = null;
    let currentContent = '';
    
    for (const para of paragraphs) {
      // Check for headers
      if (userHeaderRegex.test(para)) {
        // Save previous message if any
        if (currentRole && currentContent.trim()) {
          messages.push({
            role: currentRole,
            content: currentContent.trim()
          });
          currentContent = '';
        }
        
        // Extract content after header
        const headerMatch = para.match(userHeaderRegex);
        if (headerMatch) {
          const headerEnd = headerMatch.index + headerMatch[0].length;
          currentContent = para.substring(headerEnd).trim();
        } else {
          currentContent = '';
        }
        
        currentRole = 'user';
        
      } else if (assistantHeaderRegex.test(para)) {
        // Save previous message if any
        if (currentRole && currentContent.trim()) {
          messages.push({
            role: currentRole,
            content: currentContent.trim()
          });
          currentContent = '';
        }
        
        // Extract content after header
        const headerMatch = para.match(assistantHeaderRegex);
        if (headerMatch) {
          const headerEnd = headerMatch.index + headerMatch[0].length;
          currentContent = para.substring(headerEnd).trim();
        } else {
          currentContent = '';
        }
        
        currentRole = 'assistant';
        
      } else if (currentRole) {
        // Add to current content
        currentContent += '\n\n' + para;
      } else if (para.length > 20) {
        // If no role yet but substantial content, assume it's the user
        currentRole = 'user';
        currentContent = para;
      }
    }
    
    // Save the final message
    if (currentRole && currentContent.trim()) {
      messages.push({
        role: currentRole,
        content: currentContent.trim()
      });
    }
    
    // If we still couldn't extract messages, try a simple splitting approach
    if (messages.length === 0) {
      this.extractSimpleSplit(text, messages);
    }
  }
  
  /**
   * Extract messages from simple text splitting
   * @param {string} text - Plain text
   * @param {Array} messages - Array to store messages
   */
  static extractSimpleSplit(text, messages) {
    // Remove common UI text
    text = text.replace(/OpenAI|ChatGPT|GPT-4o|4o|Deep research|Create image|Share|Search/g, '');
    
    // Split on obvious markers if possible, or just double line breaks
    const sections = text.split(/\n\s*\n+/).filter(s => s.trim().length > 10);
    
    if (sections.length === 0) {
      return;
    }
    
    console.log('Using simple text split extraction with', sections.length, 'sections');
    
    // Assume alternating conversation starting with user
    let role = 'user';
    
    for (const section of sections) {
      const trimmed = section.trim();
      
      // Skip very short sections
      if (trimmed.length < 10) continue;
      
      // Skip UI elements and metadata
      if (trimmed.match(/OpenAI|ChatGPT|4o|GPT-4o|Deep research|Create image|Share|Search|sidebar/i)) {
        continue;
      }
      
      messages.push({
        role,
        content: trimmed
      });
      
      // Alternate roles
      role = role === 'user' ? 'assistant' : 'user';
    }
  }
  
  
  /**
   * Simpler content extraction as a last resort
   * @param {HTMLElement} container - HTML container
   * @param {Array} messages - Messages array to populate
   */
  static extractSimpleContent(container, messages) {
    // For really challenging content, just try to grab anything meaningful
    
    // First attempt: Look for any divs with substantial content
    const contentDivs = Array.from(container.querySelectorAll('div, p'))
      .filter(div => {
        const text = div.textContent.trim();
        return text.length > 50 && 
               !text.match(/OpenAI|ChatGPT|GPT-4o|4o|Deep research|Create image|Share|Search|sidebar/i);
      })
      .sort((a, b) => b.textContent.length - a.textContent.length);
    
    if (contentDivs.length > 0) {
      console.log('Found', contentDivs.length, 'content divs');
      
      // Get the largest div by content length
      const mainContent = contentDivs[0].textContent.trim();
      
      // Split by double line breaks to see if we can extract a conversation
      const paragraphs = mainContent.split(/\n\s*\n+/)
        .map(p => p.trim())
        .filter(p => p.length > 20);
      
      if (paragraphs.length >= 2) {
        // Assume it's a conversation with alternating messages
        let role = 'user';
        
        for (const paragraph of paragraphs) {
          messages.push({
            role,
            content: paragraph
          });
          
          // Alternate roles
          role = role === 'user' ? 'assistant' : 'user';
        }
      } else if (paragraphs.length === 1) {
        // Just a single block of content - assume it's from the assistant
        messages.push({
          role: 'assistant',
          content: paragraphs[0]
        });
      }
    } else {
      // Last resort - just grab the body text
      const bodyText = container.textContent.trim();
      
      if (bodyText.length > 0) {
        console.log('Using body text as fallback');
        
        messages.push({
          role: 'assistant',
          content: bodyText
        });
      }
    }
  }
  
  /**
   * Process message content to fix formatting issues
   * @param {HTMLElement} element - Element containing message content
   * @returns {string} - Processed content
   */
  static processMessageContent(element) {
    // Create a clone we can modify
    const container = element.cloneNode(true);
    
    // Pre-process code blocks
    this.processCodeBlocks(container);
    
    // Process headings
    this.processHeadings(container);
    
    // Process lists
    this.processLists(container);
    
    // Convert to markdown
    return this.elementToMarkdown(container);
  }
  
  /**
   * Process code blocks for proper formatting
   * @param {HTMLElement} container - Container element
   */
  static processCodeBlocks(container) {
    // Language patterns to recognize
    const languageIdentifiers = [
      'javascript', 'js', 'typescript', 'ts', 'python', 'py', 'java', 
      'cpp', 'c#', 'csharp', 'ruby', 'rb', 'php', 'go', 'golang', 
      'rust', 'html', 'css', 'json', 'yaml', 'yml', 'bash', 'shell', 'sh', 
      'sql', 'markdown', 'md'
    ];
    
    // First identify and mark language identifiers (common in ChatGPT output)
    const paragraphs = container.querySelectorAll('p, div, span');
    
    for (const p of paragraphs) {
      const text = p.textContent.trim();
      
      // Check if this is just a language identifier
      if (languageIdentifiers.includes(text.toLowerCase())) {
        // Mark it for special processing
        p.setAttribute('data-language-marker', text.toLowerCase());
        
        // Look for a code block after this language marker
        let nextElement = p.nextElementSibling;
        while (nextElement) {
          if (this.isCodeBlock(nextElement)) {
            // Mark the code block with this language
            nextElement.setAttribute('data-language', text.toLowerCase());
            break;
          }
          
          // Skip empty elements or spacing elements
          if (!nextElement.textContent.trim() || 
              nextElement.tagName === 'BR' ||
              nextElement.classList.contains('inline')) {
            nextElement = nextElement.nextElementSibling;
          } else {
            break;
          }
        }
      }
    }
    
    // Remove standalone language markers
    container.querySelectorAll('[data-language-marker]').forEach(el => {
      el.remove();
    });
    
    // Now process all code blocks
    const codeBlocks = Array.from(container.querySelectorAll('pre, code'));
    const potentialCodeBlocks = Array.from(container.querySelectorAll('div[class*="bg-black"], div[class*="bg-gray"], .code-block, .whitespace-pre'));
    
    // Combine both lists
    const allCodeElements = [...codeBlocks, ...potentialCodeBlocks];
    
    for (const element of allCodeElements) {
      if (this.isCodeBlock(element) && !element.getAttribute('data-processed')) {
        this.transformToCodeBlock(element);
      }
    }
  }
  
  /**
   * Check if an element is likely a code block
   * @param {HTMLElement} element - Element to check
   * @returns {boolean} - True if element is likely a code block
   */
  static isCodeBlock(element) {
    // Check tag
    if (element.tagName === 'PRE' || 
        element.tagName === 'CODE' && element.parentNode.tagName !== 'PRE' && element.textContent.includes('\n')) {
      return true;
    }
    
    // Check classes
    if (element.classList.contains('code-block') || 
        element.classList.contains('whitespace-pre') ||
        element.classList.contains('bg-black') ||
        element.classList.contains('bg-gray')) {
      return true;
    }
    
    // Check content characteristics
    const text = element.textContent;
    if (text.includes('\n') && (
        text.includes('{') && text.includes('}') ||
        text.includes('[') && text.includes(']') ||
        text.includes('function') && text.includes('(') && text.includes(')') ||
        text.includes('def ') && text.includes(':') ||
        text.includes('class ') && text.includes(':') ||
        text.includes('import ') ||
        text.includes('const ') ||
        text.includes('let ') ||
        text.includes('var ')
    )) {
      return true;
    }
    
    return false;
  }
  
  /**
   * Transform an element to a proper code block
   * @param {HTMLElement} element - Element to transform
   */
  static transformToCodeBlock(element) {
    // Mark as processed
    element.setAttribute('data-processed', 'true');
    
    // Get the language if any
    let language = element.getAttribute('data-language') || '';
    
    // Try to detect language from classes
    if (!language && element.className) {
      const matches = element.className.match(/language[-_](\w+)/i);
      if (matches) {
        language = matches[1].toLowerCase();
      }
    }
    
    // Get content
    let content = element.innerText || element.textContent;
    
    // Try to detect language from content if not already set
    if (!language) {
      language = this.detectLanguageFromContent(content);
    }
    
    // Create a new pre element
    const pre = document.createElement('pre');
    pre.className = 'code-block';
    pre.setAttribute('data-language', language);
    
    // Create a code element
    const code = document.createElement('code');
    if (language) {
      code.className = `language-${language}`;
    }
    
    code.textContent = content.trim();
    pre.appendChild(code);
    
    // Replace the original element
    if (element.parentNode) {
      element.parentNode.replaceChild(pre, element);
    }
  }
  
  /**
   * Detect programming language from code content
   * @param {string} content - Code content
   * @returns {string} - Detected language or empty string
   */
  static detectLanguageFromContent(content) {
    const firstLine = content.split('\n')[0].trim();
    
    // Check if first line indicates language
    const languageIdentifiers = [
      'javascript', 'js', 'typescript', 'ts', 'python', 'py', 'java', 
      'cpp', 'c#', 'csharp', 'ruby', 'rb', 'php', 'go', 'golang', 
      'rust', 'html', 'css', 'json', 'yaml', 'yml', 'bash', 'shell', 'sh', 
      'sql', 'markdown', 'md'
    ];
    
    if (languageIdentifiers.includes(firstLine.toLowerCase())) {
      return firstLine.toLowerCase();
    }
    
    // Use heuristics to detect language
    if (content.includes('function ') && (content.includes('{') || content.includes('=>'))) {
      return 'javascript';
    } else if (content.includes('import ') && content.includes(' from ')) {
      return 'javascript'; // Might be JS or TS
    } else if (content.includes('def ') && content.includes(':')) {
      return 'python';
    } else if (content.includes('class ') && content.includes(':')) {
      return 'python';
    } else if (content.includes('package ') && content.includes('func ')) {
      return 'go';
    } else if (content.includes('using namespace') || content.includes('#include')) {
      return 'cpp';
    } else if (content.includes('<html') || content.includes('</div>')) {
      return 'html';
    } else if (content.includes('@media') || content.includes('{') && content.includes(':')) {
      return 'css';
    } else if ((content.startsWith('{') && content.includes('}')) ||
               (content.startsWith('[') && content.includes(']'))) {
      try {
        JSON.parse(content.trim());
        return 'json';
      } catch (e) {
        // Not valid JSON
      }
    } else if (content.includes(':') && content.includes('-') && !content.includes('{')) {
      return 'yaml';
    } else if (content.includes('#!/bin/') || content.includes('$ ')) {
      return 'bash';
    }
    
    return '';
  }
  
  /**
   * Process headings for consistent formatting
   * @param {HTMLElement} container - Container element
   */
  static processHeadings(container) {
    const headings = container.querySelectorAll('h1, h2, h3, h4, h5, h6');
    
    for (const heading of headings) {
      // Fix any broken text in headings
      const text = heading.textContent.trim();
      if (text.includes('\n')) {
        heading.textContent = text.replace(/\s*\n\s*/g, ' ');
      }
    }
  }
  
  /**
   * Process lists for consistent formatting
   * @param {HTMLElement} container - Container element
   */
  static processLists(container) {
    const listItems = container.querySelectorAll('li');
    
    for (const item of listItems) {
      // Fix broken line breaks in list items
      const html = item.innerHTML;
      if (html.includes('<br>')) {
        item.innerHTML = html.replace(/<br>\s*/g, ' ');
      }
    }
  }
  
  /**
   * Convert element to markdown
   * @param {HTMLElement} element - Element to convert
   * @returns {string} - Markdown text
   */
  static elementToMarkdown(element) {
    // Start with a fresh string
    let markdown = '';
    
    // Process all child nodes
    for (const node of element.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) {
        // Text node - add text as is
        markdown += node.textContent;
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        // Element node - handle by tag
        const tagName = node.nodeName.toLowerCase();
        
        // Special handling for code blocks
        if (tagName === 'pre' && node.classList.contains('code-block')) {
          const language = node.getAttribute('data-language') || '';
          const code = node.querySelector('code')?.textContent || node.textContent;
          markdown += `\n\n\`\`\`${language}\n${code.trim()}\n\`\`\`\n\n`;
          continue;
        }
        
        // Handle by tag type
        switch (tagName) {
          case 'p':
            markdown += this.elementToMarkdown(node) + '\n\n';
            break;
          case 'h1':
            markdown += `\n\n# ${this.elementToMarkdown(node)}\n\n`;
            break;
          case 'h2':
            markdown += `\n\n## ${this.elementToMarkdown(node)}\n\n`;
            break;
          case 'h3':
            markdown += `\n\n### ${this.elementToMarkdown(node)}\n\n`;
            break;
          case 'h4':
            markdown += `\n\n#### ${this.elementToMarkdown(node)}\n\n`;
            break;
          case 'h5':
            markdown += `\n\n##### ${this.elementToMarkdown(node)}\n\n`;
            break;
          case 'h6':
            markdown += `\n\n###### ${this.elementToMarkdown(node)}\n\n`;
            break;
          case 'strong':
          case 'b':
            markdown += `**${this.elementToMarkdown(node)}**`;
            break;
          case 'em':
          case 'i':
            markdown += `*${this.elementToMarkdown(node)}*`;
            break;
          case 'a':
            const href = node.getAttribute('href') || '#';
            markdown += `[${this.elementToMarkdown(node)}](${href})`;
            break;
          case 'code':
            if (node.textContent.includes('\n') && node.parentNode.tagName.toLowerCase() !== 'pre') {
              // Multiline code block
              const language = '';
              markdown += `\n\n\`\`\`${language}\n${node.textContent.trim()}\n\`\`\`\n\n`;
            } else {
              // Inline code
              markdown += `\`${node.textContent}\``;
            }
            break;
          case 'pre':
            // Simple pre without language
            markdown += `\n\n\`\`\`\n${node.textContent.trim()}\n\`\`\`\n\n`;
            break;
          case 'ul':
            markdown += '\n' + this.elementToMarkdown(node) + '\n';
            break;
          case 'ol':
            markdown += '\n' + this.elementToMarkdown(node) + '\n';
            break;
          case 'li':
            const parent = node.parentNode;
            const isOrdered = parent.tagName.toLowerCase() === 'ol';
            
            if (isOrdered) {
              // Count position for ordered list
              let index = 1;
              let sibling = node.previousElementSibling;
              while (sibling) {
                if (sibling.tagName.toLowerCase() === 'li') {
                  index++;
                }
                sibling = sibling.previousElementSibling;
              }
              markdown += `${index}. ${this.elementToMarkdown(node)}\n`;
            } else {
              markdown += `- ${this.elementToMarkdown(node)}\n`;
            }
            break;
          case 'blockquote':
            const innerContent = this.elementToMarkdown(node);
            markdown += '\n\n> ' + innerContent.replace(/\n/g, '\n> ') + '\n\n';
            break;
          case 'table':
            markdown += this.tableToMarkdown(node) + '\n\n';
            break;
          case 'br':
            markdown += '\n';
            break;
          case 'div':
          case 'span':
          default:
            // Generic container - just process children
            markdown += this.elementToMarkdown(node);
        }
      }
    }
    
    return markdown;
  }
  
  /**
   * Convert table to markdown
   * @param {HTMLElement} table - Table element
   * @returns {string} - Markdown table
   */
  static tableToMarkdown(table) {
    let markdown = '\n\n';
    const rows = table.querySelectorAll('tr');
    
    if (rows.length === 0) {
      return '';
    }
    
    // Get maximum column count
    let maxColumns = 0;
    for (const row of rows) {
      const cellCount = row.querySelectorAll('th, td').length;
      maxColumns = Math.max(maxColumns, cellCount);
    }
    
    // Process rows
    rows.forEach((row, rowIndex) => {
      const cells = row.querySelectorAll('th, td');
      let rowContent = '|';
      
      // Add cells
      for (let i = 0; i < maxColumns; i++) {
        if (i < cells.length) {
          const cell = cells[i];
          const cellContent = this.elementToMarkdown(cell).replace(/\n/g, '<br>').trim();
          rowContent += ` ${cellContent} |`;
        } else {
          rowContent += '  |'; // Empty cell
        }
      }
      
      markdown += rowContent + '\n';
      
      // Add separator after header row
      if (rowIndex === 0) {
        let separator = '|';
        for (let i = 0; i < maxColumns; i++) {
          separator += ' --- |';
        }
        markdown += separator + '\n';
      }
    });
    
    return markdown;
  }
  
  /**
   * Generate complete transcript from messages
   * @param {Array} messages - Array of message objects
   * @param {string} title - Page title
   * @returns {string} - Formatted transcript
   */
  static generateTranscript(messages, title) {
    // Build the transcript
    const date = new Date().toISOString().split('T')[0];
    
    // Start with frontmatter
    let transcript = `---
title: "ChatGPT Conversation Transcript"
date: "${date}"
format: "transcript-v1.0"
---

# Conversation Transcript

`;
    
    // Group messages into exchanges
    let currentExchange = 1;
    let currentUserMessage = null;
    
    for (let i = 0; i < messages.length; i++) {
      const message = messages[i];
      
      // Preprocess message content to fix common formatting issues:
      // 1. Remove excessive blank lines
      let messageContent = message.content.trim()
        .replace(/\n{3,}/g, '\n\n')      // No more than 2 consecutive blank lines
        .replace(/^\n+|\n+$/g, '');      // Trim any leading/trailing blank lines
        
      // 2. Fix common heading patterns
      if (messageContent.includes('# ')) {
        // Make sure all headings have proper spacing
        messageContent = messageContent.replace(/(#+)([^\s#])/g, '$1 $2');
      }
      
      // 3. Ensure list items are properly formatted with no excessive spacing
      if (messageContent.includes('- ') || messageContent.includes('* ')) {
        messageContent = messageContent.replace(/^([\s]*[-*+] .+)\n\n([\s]*[-*+] .+)/gm, '$1\n$2');
      }
      
      // Update the message content
      message.content = messageContent;
      
      if (message.role === 'user') {
        // Start a new exchange with each user message
        transcript += `## Message Exchange ${currentExchange}\n\n`;
        transcript += `**User**:\n${message.content.trim()}\n\n`;
        currentUserMessage = message;
        
        // Look for a following assistant message
        if (i + 1 < messages.length && messages[i + 1].role === 'assistant') {
          // Preprocess the assistant message content (same as above)
          let assistantContent = messages[i + 1].content.trim()
            .replace(/\n{3,}/g, '\n\n')
            .replace(/^\n+|\n+$/g, '');
            
          // Fix headings and lists
          if (assistantContent.includes('# ')) {
            assistantContent = assistantContent.replace(/(#+)([^\s#])/g, '$1 $2');
          }
          
          if (assistantContent.includes('- ') || assistantContent.includes('* ')) {
            assistantContent = assistantContent.replace(/^([\s]*[-*+] .+)\n\n([\s]*[-*+] .+)/gm, '$1\n$2');
          }
          
          messages[i + 1].content = assistantContent;
          transcript += `**Assistant**:\n${messages[i + 1].content}\n\n`;
          i++; // Skip the assistant message in the next iteration
        }
        
        currentExchange++;
      } else if (message.role === 'assistant' && !currentUserMessage) {
        // Handle case where first message is from assistant
        transcript += `## Message Exchange ${currentExchange}\n\n`;
        transcript += `**User**:\n(No user message found)\n\n`;
        transcript += `**Assistant**:\n${message.content}\n\n`;
        currentExchange++;
      }
    }
    
    // Clean up the final transcript
    return this.cleanupGeneratedTranscript(transcript);
  }
  
  /**
   * Final cleanup of generated transcript
   * @param {string} transcript - Raw transcript
   * @returns {string} - Cleaned transcript
   */
  static cleanupGeneratedTranscript(transcript) {
    // First check if there's actual content
    if (!transcript || transcript.trim().length < 10) {
      console.error('Empty or near-empty transcript in cleanup');
      return this.createPlaceholderTranscript();
    }
    
    try {
      console.log('Cleaning transcript of length', transcript.length);
      
      // Fix spacing issues - first pass
      let cleaned = transcript
        // Remove excessive blank lines (more than 2 consecutive newlines)
        .replace(/\n{3,}/g, '\n\n')
        // Fix broken headings (no space after # symbols)
        .replace(/(#+)([^\s#])/g, '$1 $2')
        // Fix broken words across lines
        .replace(/(\w+)\s*\n\s*(\w{1,3}\b)/g, '$1$2')
        // Fix code blocks with wrong indentation
        .replace(/```(\w*)\s*\n\s+/g, '```$1\n')
        .replace(/\n\s+```/g, '\n```')
        // Ensure empty line after code blocks (but not excessive)
        .replace(/```\s*\n(?!$|\n)/g, '```\n\n')
        // Remove UI text
        .replace(/OpenAI|ChatGPT|GPT-4o|4o|Deep research|Create image|Share|Search|sidebar/g, '')
        // Fix broken headers
        .replace(/##(\w+)/g, '## $1')
        // Fix "ConversationTranscript" (no space)
        .replace(/# ConversationTranscript/g, '# Conversation Transcript');
      
      // Fix message headers from unofficial formatting (###### to **) 
      // First remove the leading document title that might be part of chat history
      let titleMatch = cleaned.match(/^[^\n#]*(?=\s*#{1,6}\s*(?:You|ChatGPT|User|Human|Assistant|AI)\s*said:)/i);
      if (titleMatch && titleMatch[0].trim()) {
        cleaned = cleaned.replace(titleMatch[0], '');
      }
      
      // Now transform message headers to standard format - comprehensive approach
      // Handle ###### style headers common in ChatGPT exports
      const headerPatterns = [
        { find: /^#{1,6}\s*You said:/gim, replace: '**User**:' },
        { find: /^#{1,6}\s*ChatGPT said:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*User:/gim, replace: '**User**:' },
        { find: /^#{1,6}\s*User\s+said:/gim, replace: '**User**:' },
        { find: /^#{1,6}\s*Assistant:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*Assistant\s+said:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*Human:/gim, replace: '**User**:' },
        { find: /^#{1,6}\s*AI:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*Model:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*GPT[-\s]*\d+[^:]*:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*GPT-4o[^:]*:/gim, replace: '**Assistant**:' },
        { find: /^#{1,6}\s*You:/gim, replace: '**User**:' },
        { find: /^#{1,6}\s*Me:/gim, replace: '**User**:' }
      ];
      
      // Apply all header pattern replacements
      headerPatterns.forEach(pattern => {
        cleaned = cleaned.replace(pattern.find, pattern.replace);
      });
      
      // Apply the same replacements for headers in the middle of the document
      headerPatterns.forEach(pattern => {
        const inTextPattern = new RegExp(`\\n${pattern.find.source.replace(/^\^/g, '')}`, 'gi');
        cleaned = cleaned.replace(inTextPattern, `\n\n${pattern.replace}`);
      });
      
      // Also check for headers with different formatting but same meaning
      const alternativeHeaders = [
        { find: /\n\s*USER:?\s*\n/gi, replace: '\n\n**User**:\n' },
        { find: /\n\s*ASSISTANT:?\s*\n/gi, replace: '\n\n**Assistant**:\n' },
        { find: /\n\s*HUMAN:?\s*\n/gi, replace: '\n\n**User**:\n' },
        { find: /\n\s*AI:?\s*\n/gi, replace: '\n\n**Assistant**:\n' },
        { find: /\n\s*YOU:?\s*\n/gi, replace: '\n\n**User**:\n' },
        { find: /\n\s*CHATGPT:?\s*\n/gi, replace: '\n\n**Assistant**:\n' }
      ];
      
      alternativeHeaders.forEach(pattern => {
        cleaned = cleaned.replace(pattern.find, pattern.replace);
      });
      
      // Fix section headers within messages to use ### instead of ##
      // Only within user/assistant message content (not message exchange headers)
      cleaned = cleaned.replace(/(^\*\*(?:User|Assistant)\*\*:[^\n]*\n\n)(## )/gm, '$1### ');
      
      // More aggressive section header fixing - handle cases where the pattern didn't match above
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:.*?\n\n)(## )/gs, '$1### ');
      
      // Fix nested headers within message content (increase level by one for better hierarchy)
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:.*?\n\n)(?:#{1,5} )/gs, (match, prefix, header) => {
        // Count number of # symbols and add one more
        const headerMatch = match.match(/(#{1,5}) /);
        if (headerMatch) {
          const level = headerMatch[1].length;
          const newLevel = Math.min(6, level + 1); // Keep maximum level at 6
          return prefix + '#'.repeat(newLevel) + ' ';
        }
        return match;
      });
      
      // Fix WikiLinks - convert to standard markdown links or just plain text
      cleaned = cleaned.replace(/\[\[(.*?)\]\]/g, (match, content) => {
        // If it contains a pipe for label|target, split and format as markdown link
        if (content.includes('|')) {
          const [label, target] = content.split('|');
          return `[${label.trim()}](${target.trim()})`;
        }
        // If it looks like a reference to another document, convert to a link
        else if (content.includes(' ')) {
          // Use the content as both label and sanitized target
          const target = content.trim().replace(/\s+/g, '-').toLowerCase();
          return `[${content.trim()}](${target})`;
        }
        // Otherwise, for simple terms, just return the content
        return content;
      });
      
      // Additional pass to fix WikiLinks in bullet points and other patterns
      // Handle bullet points with WikiLinks
      cleaned = cleaned.replace(/^(\s*)[-*+]\s+\[\[(.*?)\]\]/gm, (match, indent, content) => {
        if (content.includes('|')) {
          const [label, target] = content.split('|');
          return `${indent}- [${label.trim()}](${target.trim()})`;
        } else if (content.includes(' ')) {
          const target = content.trim().replace(/\s+/g, '-').toLowerCase();
          return `${indent}- [${content.trim()}](${target})`;
        }
        return `${indent}- ${content}`;
      });
      
      // Handle numbered lists with WikiLinks
      cleaned = cleaned.replace(/^(\s*\d+\.\s+)\[\[(.*?)\]\]/gm, (match, prefix, content) => {
        if (content.includes('|')) {
          const [label, target] = content.split('|');
          return `${prefix}[${label.trim()}](${target.trim()})`;
        } else if (content.includes(' ')) {
          const target = content.trim().replace(/\s+/g, '-').toLowerCase();
          return `${prefix}[${content.trim()}](${target})`;
        }
        return `${prefix}${content}`;
      });
      
      // Remove "undefined" text that sometimes appears
      cleaned = cleaned.replace(/\nundefined\n/g, '\n');
      cleaned = cleaned.replace(/\bundefined\b/g, '');
      
      // Remove common UI text patterns that might have survived
      const uiPatterns = [
        /chat history/i, /search/i, /deep research/i, 
        /create image/i, /share/i, /answer in chat/i, 
        /saved memory/i, /skip to content/i, /open sidebar/i
      ];
      
      uiPatterns.forEach(pattern => {
        cleaned = cleaned.replace(pattern, '');
      });
      
      // Compress list items - make lists more compact without excessive line breaks
      // First identify list blocks (including nested ones)
      const listBlockRegex = /^([ \t]*[-*+] .+(?:\n[ \t]*(?:[-*+] .+|\S.+))*\n?)+/gm;
      cleaned = cleaned.replace(listBlockRegex, (match) => {
        // Remove excessive blank lines between list items but preserve indentation
        return match.replace(/\n\n+/g, '\n').replace(/\n{2,}(\s*[-*+])/g, '\n$1');
      });
      
      // Fix numbered lists spacing
      const numberedListRegex = /^([ \t]*\d+\. .+(?:\n[ \t]*(?:\d+\. .+|\S.+))*\n?)+/gm;
      cleaned = cleaned.replace(numberedListRegex, (match) => {
        return match.replace(/\n\n+/g, '\n').replace(/\n{2,}(\s*\d+\.)/g, '\n$1');
      });
      
      // Additional more aggressive list item cleanup - fix spacing issues
      // This addresses the common ChatGPT pattern of inserting extra newlines in list items
      cleaned = cleaned.replace(/^(\s*[-*+]\s+[^\n]+)\n\n+(\s*[-*+]\s+)/gm, '$1\n$2');
      cleaned = cleaned.replace(/^(\s*\d+\.\s+[^\n]+)\n\n+(\s*\d+\.\s+)/gm, '$1\n$2');
      
      // Fix list items that have multiple paragraphs by indenting continuation lines
      cleaned = cleaned.replace(/^(\s*[-*+]\s+[^\n]+)\n\n+(\S)/gm, '$1\n\n  $2');
      cleaned = cleaned.replace(/^(\s*\d+\.\s+[^\n]+)\n\n+(\S)/gm, '$1\n\n  $2');
      
      // Fix language identifiers in code blocks
      // Common incorrect mappings - expanded set
      const languageFixMapping = {
        'css': '',       // Often incorrectly used for plain text
        'plaintext': '', // Remove plaintext marker
        'markdown': 'markdown',
        'json': 'json',
        'yaml': 'yaml',
        'yml': 'yaml',
        'bash': 'bash',
        'shell': 'bash',
        'sh': 'bash',
        'javascript': 'javascript',
        'js': 'javascript',
        'typescript': 'typescript',
        'ts': 'typescript',
        'python': 'python',
        'py': 'python',
        'java': 'java',
        'csharp': 'csharp',
        'c#': 'csharp',
        'php': 'php',
        'go': 'go',
        'golang': 'go',
        'ruby': 'ruby',
        'rb': 'ruby',
        'html': 'html',
        'xml': 'xml',
        'sql': 'sql',
        'text': '',      // Remove text marker
        'txt': '',       // Remove text marker
      };
      
      // Apply language fixes and ensure proper spacing within code blocks
      Object.entries(languageFixMapping).forEach(([incorrect, correct]) => {
        const pattern = new RegExp('```\\s*' + incorrect + '\\s*\n', 'gi');
        cleaned = cleaned.replace(pattern, '```' + correct + '\n');
      });
      
      // Ensure code block content starts on its own line with no extra spaces
      cleaned = cleaned.replace(/```(\w*)\s*\n\s+/g, '```$1\n');
      
      // Remove language identifier padding
      cleaned = cleaned.replace(/```\s+(\w+)\s*\n/g, '```$1\n');
      
      // Ensure there's a "Conversation Transcript" title
      if (!cleaned.includes('# Conversation Transcript')) {
        if (cleaned.includes('---\n')) {
          // If there's frontmatter, add title after it
          cleaned = cleaned.replace(/(---\s*[\s\S]*?---\s*)/m, '$1\n# Conversation Transcript\n\n');
        } else {
          // Otherwise add to beginning
          cleaned = '# Conversation Transcript\n\n' + cleaned;
        }
      }
      
      // Fix code blocks - apply specialized function
      cleaned = this.fixCodeBlocks(cleaned);
      
      // Double-check closing backticks on all code blocks
      const openCodeBlockCount = (cleaned.match(/```\w*\n/g) || []).length;
      const closeCodeBlockCount = (cleaned.match(/\n```/g) || []).length;
      
      if (openCodeBlockCount > closeCodeBlockCount) {
        // We're missing some closing backticks, add them at paragraph breaks
        const codeSections = cleaned.split(/```\w*\n/);
        if (codeSections.length > 1) {
          cleaned = '';
          for (let i = 0; i < codeSections.length; i++) {
            if (i === 0) {
              // First section before any code blocks
              cleaned += codeSections[i];
            } else {
              // A section that should end with a code block
              const section = codeSections[i];
              // Check if it already ends with a code block close
              if (!section.trim().endsWith('```')) {
                // Find a good place to end the code block
                const paragraphBreak = section.search(/\n\n/);
                if (paragraphBreak > -1) {
                  cleaned += section.substring(0, paragraphBreak) + '\n```' + section.substring(paragraphBreak);
                } else {
                  cleaned += section + '\n```';
                }
              } else {
                cleaned += section;
              }
            }
          }
        }
      }
      
      // Make sure we have at least one message exchange marker
      if (!cleaned.includes('## Message Exchange')) {
        // Check if there's content that looks like a message
        if (cleaned.includes('**User**:') || cleaned.includes('**Assistant**:')) {
          // Add a message exchange marker before the first user/assistant
          const userIndex = cleaned.indexOf('**User**:');
          const assistantIndex = cleaned.indexOf('**Assistant**:');
          
          let insertIndex;
          if (userIndex !== -1 && (assistantIndex === -1 || userIndex < assistantIndex)) {
            insertIndex = userIndex;
          } else if (assistantIndex !== -1) {
            insertIndex = assistantIndex;
          }
          
          if (insertIndex !== -1) {
            cleaned = cleaned.substring(0, insertIndex) + 
                    '## Message Exchange 1\n\n' + 
                    cleaned.substring(insertIndex);
          }
        }
      }
      
      // Ensure message headers have correct spacing
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:)(?!\n\n)/g, '$1\n\n');
      
      // Fix spacing around code blocks within messages
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:.*?\n\n)```/gs, '$1\n```');
      cleaned = cleaned.replace(/```\n\n(\*\*(?:User|Assistant)\*\*:)/g, '```\n\n\n$1');
      
      // Fix cases where a code block immediately follows a message header (with no text in between)
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:)\s*\n\s*```/g, '$1\n\n```');
      
      // Fix cases where a code block is the very last thing in a message (ensure proper spacing)
      cleaned = cleaned.replace(/```\s*\n\s*(\*\*(?:User|Assistant)\*\*:)/g, '```\n\n$1');
      
      // Fix excessive empty lines and ensure proper spacing 
      // First, remove excessive empty lines (more than 2 consecutive newlines)
      cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
      
      // Fix spacing after message role headers
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:)\s*\n{3,}/g, '$1\n\n');
      
      // Ensure proper spacing after message headers
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:)(?!\n)/g, '$1\n');
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:)\n(?!\n)/g, '$1\n\n');
      
      // Fix cases where message content starts with multiple newlines
      cleaned = cleaned.replace(/(\*\*(?:User|Assistant)\*\*:)\s*\n{3,}/g, '$1\n\n');
      
      // Fix spacing in content blocks - replace groups of empty lines with proper formatting
      const contentBlocks = cleaned.match(/(\*\*(?:User|Assistant)\*\*:.*?)(?=\*\*(?:User|Assistant)\*\*:|$)/gs) || [];
      contentBlocks.forEach(block => {
        // Process each message block for proper formatting
        let fixedBlock = block
          // Ensure exactly one empty line between paragraphs (not two)
          .replace(/\n\s*\n\s*\n+/g, '\n\n')
          // Add proper spacing after code blocks before new paragraphs
          .replace(/```\s*\n([^\n])/g, '```\n\n$1')
          // No excessive spacing before code blocks
          .replace(/([^\n])\n\n+```/g, '$1\n\n```')
          // Remove excessive blank lines at the beginning of a message
          .replace(/^(\*\*(?:User|Assistant)\*\*:)\s*\n+/m, '$1\n\n')
          // Fix list items spacing - no empty lines between items in the same list
          .replace(/^([\s]*[-*+] .+)\n\n([\s]*[-*+] .+)/gm, '$1\n$2');
          
        // Special handling for common patterns in ChatGPT
        
        // Convert arrow sequences to inline code
        fixedBlock = fixedBlock.replace(/(\w+)\s+→\s+(\w+)/g, '`$1` → `$2`');
        
        // Fix excessive spacing around lists and code blocks
        fixedBlock = fixedBlock.replace(/(```.*?```)\n\n\n+/gs, '$1\n\n');
        fixedBlock = fixedBlock.replace(/\n\n\n+([-*+] )/g, '\n\n$1');
        
        // Remove any trailing newlines at the end of the message
        fixedBlock = fixedBlock.replace(/\n+$/g, '\n');
        
        cleaned = cleaned.replace(block, fixedBlock);
      });
      
      // Fix spacing around headers
      cleaned = cleaned
        // Fix spacing after headers
        .replace(/(#{1,6}[^\n]+\n)\n{2,}/g, '$1\n')
        // Fix spacing before headers
        .replace(/\n{3,}(#{1,6})/g, '\n\n$1')
        // Ensure message exchange headers have proper spacing
        .replace(/(## Message Exchange \d+)\s*\n+/g, '$1\n\n');
      
      // Improve list formatting
      cleaned = cleaned
        // Standardize indentation in lists
        .replace(/^(\s*[-*+]\s.*\n)(\s+)([^\s-*+])/gm, '$1$3')
        // Fix list item continuations (ensure proper indentation)
        .replace(/^(\s*[-*+]\s.*\n)([^\s-*+\n])/gm, '$1  $2')
        // Fix nested list indentation
        .replace(/^(\s*[-*+]\s.*\n)(\s+[-*+])/gm, '$1$2');
      
      // Fix HTML elements spacing
      cleaned = cleaned.replace(/>\s*\n\s*\n\s*</g, '>\n<');
      
      // Fix problematic inline code within messages
      cleaned = cleaned.replace(/`([^`]+\n[^`]+?)`/g, '```\n$1\n```');
      
      // Remove problematic "Copy"/"Edit" strings that appear in ChatGPT output
      cleaned = cleaned.replace(/\bCopyEdit\b/g, '');
      cleaned = cleaned.replace(/\bCopy Edit\b/g, '');
      cleaned = cleaned.replace(/\bCopy code\b/g, '');
      
      // Clean up language identifiers that appear before code blocks
      const languageIdsBeforeBlocks = [
        'javascript', 'js', 'typescript', 'ts', 'python', 'py', 'java', 
        'cpp', 'c#', 'csharp', 'ruby', 'rb', 'php', 'go', 'golang', 
        'rust', 'html', 'css', 'json', 'yaml', 'yml', 'bash', 'shell', 'sh', 
        'sql', 'markdown', 'md', 'text', 'txt', 'plaintext', 'xml'
      ];
      
      // Handle language identifiers that appear on their own line before code
      languageIdsBeforeBlocks.forEach(lang => {
        // Match specific language identifier on a line by itself before a code block
        const langPattern = new RegExp(`^\\s*${lang}\\s*$\\s*^\\s*\`\`\``, 'gim');
        cleaned = cleaned.replace(langPattern, '```' + lang.toLowerCase());
        
        // Also match language identifier followed by colon syntax (very common in ChatGPT)
        const langColonPattern = new RegExp(`^\\s*${lang}:\\s*$\\s*^\\s*\`\`\``, 'gim');
        cleaned = cleaned.replace(langColonPattern, '```' + lang.toLowerCase());
        
        // Also match "In {language}:" pattern that sometimes appears
        const langInPattern = new RegExp(`^\\s*In\\s+${lang}:\\s*$\\s*^\\s*\`\`\``, 'gim');
        cleaned = cleaned.replace(langInPattern, '```' + lang.toLowerCase());
        
        // Also match "Using {language}:" pattern
        const langUsingPattern = new RegExp(`^\\s*Using\\s+${lang}:\\s*$\\s*^\\s*\`\`\``, 'gim');
        cleaned = cleaned.replace(langUsingPattern, '```' + lang.toLowerCase());
      });
      
      // Fix code blocks that have the language on a separate line after the opening fence
      cleaned = cleaned.replace(/```\s*\n\s*(javascript|js|typescript|ts|python|py|java|cpp|c#|csharp|ruby|rb|php|go|golang|rust|html|css|json|yaml|yml|bash|shell|sh|sql|markdown|md|text|txt|plaintext|xml)\s*\n/gi, (match, lang) => {
        return '```' + lang.toLowerCase() + '\n';
      });
      
      // Code block improvements - comprehensive approach
      cleaned = cleaned
        // First fix common broken patterns
        .replace(/(\S)\s*\n\s*```(\w*)/g, '$1\n\n```$2') // Ensure blank line before code block
        .replace(/```\s*\n([^\n`])/g, '```\n\n$1')       // Ensure blank line after code block
        // Fix empty lines inside code blocks
        .replace(/(```\w*\n)\n+/g, '$1')
        .replace(/\n+(\n```)/g, '$1')
        // Remove empty code blocks completely
        .replace(/```\w*\n\s*```/g, '')
        // Fix language identifier spacing
        .replace(/```\s+(\w+)/g, '```$1')
        // Fix code blocks with no language identifier
        .replace(/```\s*\n/g, '```\n')
        // Remove code blocks with empty/whitespace-only content
        .replace(/```(\w*)\n\s*\n*\s*```/g, '')
        // Fix problematic inline code within messages
        .replace(/`([^`]+\n[^`]+?)`/g, '```\n$1\n```')
        // Remove problematic "Copy"/"Edit" strings that appear in ChatGPT output
        .replace(/\bCopyEdit\b/g, '')
        .replace(/\bCopy Edit\b/g, '')
        .replace(/\bCopy code\b/g, '');
      
      // Fix problematic spaces around code block fences
      cleaned = cleaned.replace(/```(\w*)\s*\n/g, '```$1\n');
      cleaned = cleaned.replace(/\n\s*```/g, '\n```');
      
      // Handle special code blocks for single words/commands (very common in ChatGPT)
      cleaned = cleaned.replace(/```\n([a-zA-Z0-9_-]{1,20})\n```/g, '`$1`');
      
      // Handle code blocks with language on a separate line
      cleaned = cleaned.replace(/```\n([a-zA-Z0-9_-]{1,20})\n([\s\S]*?)\n```/g, (match, possibleLang, content) => {
        // Check if the first line looks like a language identifier
        if (languageIdsBeforeBlocks.includes(possibleLang.toLowerCase())) {
          return '```' + possibleLang.toLowerCase() + '\n' + content + '\n```';
        }
        return match; // No change needed
      });
      
      // Normalize indentation inside code blocks
      const codeBlockRegex = /```(\w*)\n([\s\S]*?)\n```/g;
      let codeBlockMatches = [...cleaned.matchAll(codeBlockRegex)];
      
      for (const match of codeBlockMatches) {
        const [fullMatch, language, content] = match;
        
        // Check if content is whitespace only
        if (content.trim() === '') {
          cleaned = cleaned.replace(fullMatch, '');
          continue;
        }
        
        // Normalize indentation in the content
        const lines = content.split('\n');
        
        // Find minimum indentation (excluding empty lines)
        let minIndent = Infinity;
        for (const line of lines) {
          if (line.trim() === '') continue;
          const indent = line.search(/\S/);
          if (indent !== -1 && indent < minIndent) {
            minIndent = indent;
          }
        }
        
        // If we found a minimum indentation, remove it from all lines
        if (minIndent !== Infinity && minIndent > 0) {
          const normalizedContent = lines.map(line => {
            if (line.trim() === '') return '';
            return line.substring(Math.min(line.search(/\S/), minIndent));
          }).join('\n');
          
          cleaned = cleaned.replace(fullMatch, '```' + language + '\n' + normalizedContent + '\n```');
        }
      }
      
      // Fix unintended markdown conflicts
      cleaned = cleaned
        // Fix unintended headers (# used as first character without intending to create a header)
        .replace(/^([-*+]\s+)#(\s+[^#])/gm, '$1\\#$2')
        // Fix unintended emphasis 
        .replace(/(\w)\*\*(\w)/g, '$1 **$2')
        .replace(/(\w)\*(\w)/g, '$1 *$2');
        
      // Fix message header styles (user should be bold)
      cleaned = cleaned
        .replace(/\*\*User\*\*:/g, '**User**:')
        .replace(/\*\*Assistant\*\*:/g, '**Assistant**:');
      
      // Final cleanup - trim any trailing whitespace
      return cleaned.trim();
    
    } catch (error) {
      console.error('Error in cleanupGeneratedTranscript:', error);
      return transcript.trim(); // Return original if cleanup fails
    }
  }
  
  /**
   * Create a placeholder transcript
   * @returns {string} - Placeholder transcript
   */
  static createPlaceholderTranscript() {
    const date = new Date().toISOString().split('T')[0];
    
    return `---
title: "ChatGPT Conversation Transcript"
date: "${date}"
format: "transcript-v1.0"
---

# Conversation Transcript

## Message Exchange 1

**User**:
(Could not extract user message)

**Assistant**:
(Could not extract assistant response)

Note: The converter was unable to properly extract the conversation content. Please try using the converter directly on a ChatGPT conversation page.
`;
  }
  
  
  /**
   * Check if the HTML is from ChatGPT
   * @param {string} html - HTML content
   * @returns {boolean} - True if the content is from ChatGPT
   */
  static isChatGPT(html) {
    // URL-based detection
    if (
      html.includes('chatgpt.com') ||
      html.includes('chat.openai.com') ||
      html.includes('openai.com/chat') ||
      (typeof window !== 'undefined' && window.location.hostname.includes('chat.openai.com'))
    ) {
      return true;
    }
    
    // Content structure detection
    if (
      html.includes('data-message-author-role="user"') ||
      html.includes('data-message-author-role="assistant"') ||
      html.includes('data-testid="conversation-turn"') ||
      html.includes('data-testid="conversation-turn-')
    ) {
      return true;
    }
    
    // Message patterns detection
    if (
      html.includes('You said:') ||
      html.includes('ChatGPT said:') ||
      html.includes('Human:') && html.includes('Assistant:') ||
      html.includes('User:') && html.includes('AI:') ||
      html.includes('**User**:') && html.includes('**Assistant**:') ||
      html.includes('user-message') ||
      html.includes('assistant-message')
    ) {
      return true;
    }
    
    // UI class detection
    if (
      html.includes('markdown prose') || // ChatGPT markdown container
      html.includes('whitespace-pre-wrap') && html.includes('markdown') ||
      html.includes('react-scroll') && html.includes('chat-message')
    ) {
      return true;
    }
    
    // Already processed content detection
    if (
      html.includes('title: "ChatGPT Conversation Transcript"') ||
      html.includes('format: "transcript-v1.0"') ||
      html.includes('## Message Exchange') && (html.includes('**User**:') || html.includes('**Assistant**:'))
    ) {
      return true;
    }
    
    // OpenAI model mentions
    if (
      html.includes('GPT-4') ||
      html.includes('GPT-3.5') ||
      html.includes('GPT-4o') ||
      html.includes('gpt-4-turbo')
    ) {
      // Additional check to avoid false positives - look for chat structure
      return html.includes('message') || html.includes('conversation') || html.includes('chat');
    }
    
    return false;
  }
}

// Export for use in other scripts
if (typeof module !== 'undefined') {
  module.exports = TranscriptConverter;
}