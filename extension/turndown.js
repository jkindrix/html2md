/**
 * GRAB2MD TurndownService - Enhanced HTML to Markdown converter
 * Derived from Turndown v7.1.1
 * Copyright (c) 2017 Dom Christie
 * Licensed under the MIT License; see THIRD_PARTY_NOTICES.md.
 *
 * Enhanced for GRAB2MD extension with improved formatting and additional rules
 */
var TurndownService = (function () {
  'use strict';

  /**
   * Helper utility functions
   */

  // Merge objects
  function extend(destination) {
    for (var i = 1; i < arguments.length; i++) {
      var source = arguments[i];
      for (var key in source) {
        if (source.hasOwnProperty(key)) destination[key] = source[key];
      }
    }
    return destination;
  }

  // Create a string by repeating a character
  function repeat(character, count) {
    return Array(count + 1).join(character);
  }

  // Trim leading newlines from a string
  function trimLeadingNewlines(string) {
    return string.replace(/^\n*/, '');
  }

  // Trim trailing newlines from a string
  function trimTrailingNewlines(string) {
    return string.replace(/\n*$/, '');
  }

  // Preserve authored Markdown punctuation as literal text. Line-leading
  // escapes are intentionally narrower so ordinary prose punctuation remains
  // readable in the generated source.
  function escapeMarkdown(string) {
    return string
      .replace(/\\/g, '\\\\')
      .replace(/\*/g, '\\*')
      .replace(/_/g, '\\_')
      .replace(/`/g, '\\`')
      .replace(/\[/g, '\\[')
      .replace(/\]/g, '\\]')
      .replace(/^(\s*)([-+]) /gm, '$1\\$2 ')
      .replace(/^(\s*)(#{1,6}) /gm, '$1\\$2 ')
      .replace(/^(\s*)> /gm, '$1\\> ')
      .replace(/^(\s*)(\d+)\. /gm, '$1$2\\. ');
  }
  
  // Detect if string content appears to be code for proper code fence handling
  function detectCodeLanguage(content) {
    // Common language detection patterns
    const patterns = {
      javascript: /\b(var|let|const|function|return|if|for|while|class|import|export|async|await)\b/i,
      python: /\b(def|import|from|class|if|for|while|with|return|yield)\b/i,
      html: /^\s*<(!DOCTYPE|html|div|p|span|table|h[1-6])/i,
      css: /\b(body|margin|padding|font-size|color|background|@media|\.[\w-]+|#[\w-]+)\b/i,
      json: /^\s*[{\[]/,
      bash: /^\s*(cd|ls|grep|git|npm|yarn|python|mkdir|rm|chmod|sudo)/i,
      markdown: /^\s*(#{1,6}\s|[*-]\s|\d+\.\s|>|```)/i,
      yaml: /^(\s*[\w-]+\s*:|---)/i
    };
    
    // Test content against language patterns
    for (const [lang, pattern] of Object.entries(patterns)) {
      if (pattern.test(content)) {
        return lang;
      }
    }
    
    return '';  // No specific language detected
  }

  /**
   * Element type definitions
   */
  var blockElements = [
    'ADDRESS', 'ARTICLE', 'ASIDE', 'AUDIO', 'BLOCKQUOTE', 'BODY', 'CANVAS',
    'CENTER', 'DD', 'DIR', 'DIV', 'DL', 'DT', 'FIELDSET', 'FIGCAPTION', 'FIGURE',
    'FOOTER', 'FORM', 'FRAMESET', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'HEADER',
    'HGROUP', 'HR', 'HTML', 'ISINDEX', 'LI', 'MAIN', 'MENU', 'NAV', 'NOFRAMES',
    'NOSCRIPT', 'OL', 'OUTPUT', 'P', 'PRE', 'SECTION', 'TABLE', 'TBODY', 'TD',
    'TFOOT', 'TH', 'THEAD', 'TR', 'UL'
  ];

  var voidElements = [
    'AREA', 'BASE', 'BR', 'COL', 'COMMAND', 'EMBED', 'HR', 'IMG', 'INPUT',
    'KEYGEN', 'LINK', 'META', 'PARAM', 'SOURCE', 'TRACK', 'WBR'
  ];

  var meaningfulWhenBlankElements = [
    'A', 'TABLE', 'THEAD', 'TBODY', 'TFOOT', 'TH', 'TD', 'IFRAME', 'SCRIPT',
    'AUDIO', 'VIDEO', 'BUTTON', 'DETAILS', 'DIALOG', 'RUBY', 'FIGURE', 'METER'
  ];

  /**
   * Element type checking functions
   */
  function isBlock(node) {
    return is(node, blockElements);
  }

  function isVoid(node) {
    return is(node, voidElements);
  }

  function hasVoid(node) {
    return has(node, voidElements);
  }

  function isMeaningfulWhenBlank(node) {
    return is(node, meaningfulWhenBlankElements);
  }

  function is(node, tagNames) {
    return tagNames.indexOf(node.nodeName) >= 0;
  }

  function has(node, tagNames) {
    return node.getElementsByTagName && tagNames.some(function (tagName) {
      return node.getElementsByTagName(tagName).length;
    });
  }

  /**
   * Conversion rules
   */
  var rules = {};

  // Basic elements
  rules.paragraph = {
    filter: 'p',
    replacement: function (content) {
      return '\n\n' + content + '\n\n';
    }
  };

  rules.lineBreak = {
    filter: 'br',
    replacement: function (content, node, options) {
      return options.br + '\n';
    }
  };

  rules.heading = {
    filter: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
    replacement: function (content, node, options) {
      var hLevel = Number(node.nodeName.charAt(1));

      // Skip empty headings
      if (!content.trim()) {
        return '\n\n';
      }

      if (options.headingStyle === 'setext' && hLevel < 3) {
        var underline = repeat((hLevel === 1 ? '=' : '-'), content.length);
        return '\n\n' + content + '\n' + underline + '\n\n';
      } else {
        return '\n\n' + repeat('#', hLevel) + ' ' + content + '\n\n';
      }
    }
  };

  rules.blockquote = {
    filter: 'blockquote',
    replacement: function (content) {
      content = content.replace(/^\n+|\n+$/g, '');
      content = content.replace(/^/gm, '> ');
      return '\n\n' + content + '\n\n';
    }
  };

  // Lists
  rules.list = {
    filter: ['ul', 'ol'],
    replacement: function (content, node) {
      var parent = node.parentNode;
      if (parent.nodeName === 'LI' && parent.lastElementChild === node) {
        return '\n' + content;
      } else {
        return '\n\n' + content + '\n\n';
      }
    }
  };

  rules.listItem = {
    filter: 'li',
    replacement: function (content, node, options) {
      content = content
        .replace(/^\n+/, '')
        .replace(/\n+$/, '\n')
        .replace(/\n/gm, '\n    ');

      // Remove extra blank lines
      content = content.replace(/^\s*\n\s*\n/gm, '\n');

      var prefix = options.bulletListMarker + ' ';
      var parent = node.parentNode;

      if (parent.nodeName === 'OL') {
        var start = parent.getAttribute('start');
        var index = Array.prototype.indexOf.call(parent.children, node);
        prefix = (start ? Number(start) + index : index + 1) + '. ';
      }

      return prefix + content + (node.nextSibling && !/\n$/.test(content) ? '\n' : '');
    }
  };

  // Code blocks and inline code
  rules.codeBlock = {
    filter: function (node) {
      return node.nodeName === 'PRE' && node.firstChild && node.firstChild.nodeName === 'CODE';
    },
    replacement: function (content, node, options) {
      // Handle empty blocks
      if (!content.trim()) {
        return '\n\n';
      }
      
      var language = '';
      
      // Try to detect language from classes
      if (node.firstChild && node.firstChild.className) {
        var className = node.firstChild.className || '';
        language = (className.match(/language-(\S+)/) || [null, ''])[1];
      }
      
      // Also check node's own class for language indicators
      if (!language && node.className) {
        language = (node.className.match(/language-(\S+)/) || [null, ''])[1];
      }
      
      // Try to get language from a nearby language indicator.
      if (!language) {
        var prevEl = node.previousElementSibling;
        if (prevEl && (prevEl.textContent.match(/^(javascript|python|java|cpp|c\+\+|typescript|ruby|go|rust|php|html|css|json|yaml|bash|shell|sql)$/i))) {
          language = prevEl.textContent.trim().toLowerCase();
        }
      }
      
      // If no language specified but content looks like code, try to detect it
      if (!language) {
        language = detectCodeLanguage(content);
      }
      
      // Clean the content - remove excess whitespace and normalize line endings
      var code = content.replace(/^\s+|\s+$/g, '');
      
      // Create the appropriate fenced code block
      if (options.codeBlockStyle === 'fenced') {
        var fence = options.fence || '```';
        
        // Ensure fence is ```
        fence = '```';
        
        // If the code contains backticks, consider using a different fence character
        if (code.indexOf('```') !== -1) {
          fence = '~~~';
        }
        
        return (
          '\n\n' + fence + (language ? language : '') + '\n' +
          code + 
          '\n' + fence + '\n\n'
        );
      } else {
        // Indented code block
        return '\n\n    ' + code.replace(/\n/g, '\n    ') + '\n\n';
      }
    }
  };

  rules.inlineCode = {
    filter: function (node) {
      return node.nodeName === 'CODE' && !(node.parentNode.nodeName === 'PRE');
    },
    replacement: function (content) {
      content = content.replace(/\r?\n/g, ' ');
      // Use double backticks if the content itself contains a backtick
      if (content.indexOf('`') !== -1) {
        return '`` ' + content + ' ``';
      }
      return '`' + content + '`';
    }
  };

  // Links and images
  rules.image = {
    filter: 'img',
    replacement: function (content, node) {
      var alt = node.alt || '';
      var src = node.getAttribute('src') || '';
      var title = node.title || '';
      var titlePart = title ? ' "' + title + '"' : '';

      // Handle missing src attribute
      if (!src) return '';

      // Check if image is a decoration or small icon - skip those
      var width = node.getAttribute('width') || node.style.width || '';
      var height = node.getAttribute('height') || node.style.height || '';

      // Skip likely decorative or tiny images
      if ((width && parseInt(width) < 20) || (height && parseInt(height) < 20)) {
        return '';
      }

      return src ? '![' + alt + ']' + '(' + src + titlePart + ')' : '';
    }
  };

  rules.link = {
    filter: function (node, options) {
      return options.linkStyle === 'inlined' &&
             node.nodeName === 'A' &&
             node.getAttribute('href');
    },
    replacement: function (content, node) {
      var href = node.getAttribute('href');
      var title = node.title ? ' "' + node.title + '"' : '';

      // Skip empty links or anchors that don't point anywhere
      if (!href || href === '#' || href.startsWith('javascript:')) {
        return content;
      }

      // Skip empty content links that are likely just decorative
      if (!content.trim()) {
        return '';
      }

      return '[' + content + '](' + href + title + ')';
    }
  };

  // Tables
  rules.table = {
    filter: 'table',
    replacement: function (content, node) {
      // Check if the table is empty or only has empty cells
      if (!content.trim() || content.replace(/\|/g, '').trim() === '') {
        return '\n\n';
      }

      var rows = node.rows;
      var columnCount = 0;
      var tableContent = '';

      // Find the maximum number of columns
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].cells.length > columnCount) {
          columnCount = rows[i].cells.length;
        }
      }

      // If no columns, skip the table
      if (columnCount === 0) return '\n\n';

      // Process each row
      for (var rowIndex = 0; rowIndex < rows.length; rowIndex++) {
        var row = rows[rowIndex];
        var cells = row.cells;

        if (cells.length === 0) continue;

        var rowContent = '|';

        // Process each cell in the row
        for (var cellIndex = 0; cellIndex < columnCount; cellIndex++) {
          var cellContent = '';

          if (cellIndex < cells.length) {
            var cell = cells[cellIndex];
            cellContent = escapeMarkdown(cell.textContent.trim())
              .replace(/\r\n?|\n/g, '<br>')
              .replace(/\|/g, '\\|');
          }

          rowContent += ' ' + cellContent + ' |';
        }

        // Add row separator for header row
        if (rowIndex === 0) {
          var separatorRow = '|';
          for (var k = 0; k < columnCount; k++) {
            separatorRow += ' --- |';
          }
          tableContent += rowContent + '\n' + separatorRow;
        } else {
          tableContent += rowContent;
        }

        tableContent += '\n';
      }

      return '\n\n' + tableContent + '\n\n';
    }
  };

  // Additional formatting elements
  rules.emphasis = {
    filter: ['em', 'i'],
    replacement: function (content, node, options) {
      if (!content.trim()) return '';
      return options.emDelimiter + content + options.emDelimiter;
    }
  };

  rules.strong = {
    filter: ['strong', 'b'],
    replacement: function (content, node, options) {
      if (!content.trim()) return '';
      return '**' + content + '**';
    }
  };

  rules.strikethrough = {
    filter: ['del', 's'],
    replacement: function (content) {
      if (!content.trim()) return '';
      return '~~' + content + '~~';
    }
  };

  rules.horizontalRule = {
    filter: 'hr',
    replacement: function (content, node, options) {
      return '\n\n' + options.hr + '\n\n';
    }
  };

  // Special cases
  rules.div = {
    filter: 'div',
    replacement: function (content) {
      return content ? '\n\n' + content + '\n\n' : '\n\n';
    }
  };

  rules.span = {
    filter: 'span',
    replacement: function (content) {
      return content || '';
    }
  };

  // Captions and figures
  rules.figure = {
    filter: 'figure',
    replacement: function (content, node) {
      // Try to identify caption
      var figcaption = node.querySelector('figcaption');
      var caption = figcaption ? figcaption.textContent.trim() : '';

      // If there's a caption, add it after the content
      if (caption) {
        return '\n\n' + content + '\n\n*' + caption + '*\n\n';
      }

      return '\n\n' + content + '\n\n';
    }
  };

  /**
   * TurndownService Constructor
   * @param {Object} options - Configuration options
   */
  function TurndownService(options) {
    if (!(this instanceof TurndownService)) return new TurndownService(options);

    var defaults = {
      headingStyle: 'atx',
      hr: '---',
      bulletListMarker: '-',
      codeBlockStyle: 'fenced',
      fence: '```',
      emDelimiter: '_',
      strongDelimiter: '**',
      linkStyle: 'inlined',
      linkReferenceStyle: 'full',
      br: '  ',
      blankReplacement: function (content, node) {
        return node.isBlock ? '\n\n' : '';
      },
      keepReplacement: function (content, node) {
        return node.isBlock ? '\n\n' + node.outerHTML + '\n\n' : node.outerHTML;
      },
      defaultReplacement: function (content, node) {
        return node.isBlock ? '\n\n' + content + '\n\n' : content;
      }
    };

    this.options = extend({}, defaults, options);
    this.rules = extend({}, rules);

    // Additional rules can be defined here
  }

  /**
   * Convert HTML to Markdown
   * @param {String|Node} input - HTML string or DOM node to convert
   * @returns {String} - Markdown output
   */
  TurndownService.prototype.turndown = function (input) {
    if (!input) return '';

    var root;

    if (typeof input === 'string') {
      // Parse page-controlled markup in an inert document. Assigning to an
      // element owned by the extension popup document can initiate passive
      // resource requests even while the element is detached. Process the
      // parsed body directly instead of wrapping page input in a sentinel
      // element: page markup could otherwise close that wrapper early and
      // silently omit the remaining content.
      var parser = new DOMParser();
      var parsed = parser.parseFromString(input, 'text/html');
      root = parsed.body;
    } else {
      root = input.cloneNode(true);
    }

    var output = this.process(root);

    // Remove only conversion-boundary line breaks. Global Markdown cleanup is
    // deliberately avoided because it cannot distinguish prose/list spacing
    // from authored whitespace inside generated code blocks.
    return output.replace(/^[\r\n]+|[\r\n]+$/g, '');
  };

  /**
   * Process a node and its children into Markdown
   * @param {Node} node - The node to process
   * @returns {String} - Markdown output
   */
  TurndownService.prototype.process = function (node) {
    var output = '';

    // Process each child node
    for (var i = 0; i < node.childNodes.length; i++) {
      var childNode = node.childNodes[i];
      output += this.processNode(childNode);
    }

    return output;
  };

  /**
   * Process a single node into Markdown
   * @param {Node} node - The node to process
   * @returns {String} - Markdown output
   */
  TurndownService.prototype.processNode = function (node) {
    var output = '';

    if (node.nodeType === 1) {
      // Element node
      node.isBlock = isBlock(node);

      var rule = this.findMatchingRule(node);

      if (rule) {
        output = rule.replacement(this.process(node), node, this.options);
      } else if (isVoid(node)) {
        output = '';
      } else {
        output = this.options.defaultReplacement(this.process(node), node);
      }
    } else if (node.nodeType === 3) {
      // Text node
      var parentName = node.parentNode && node.parentNode.nodeName;
      output = parentName === 'CODE' || parentName === 'PRE'
        ? node.nodeValue
        : escapeMarkdown(node.nodeValue);
    }

    return output;
  };

  /**
   * Find the rule that matches a given node
   * @param {Node} node - The node to match
   * @returns {Object|null} - The matching rule or null
   */
  TurndownService.prototype.findMatchingRule = function (node) {
    for (var key in this.rules) {
      var rule = this.rules[key];
      var filter = rule.filter;

      if (typeof filter === 'string') {
        if (filter === node.nodeName.toLowerCase()) return rule;
      } else if (Array.isArray(filter)) {
        if (filter.indexOf(node.nodeName.toLowerCase()) >= 0) return rule;
      } else if (typeof filter === 'function') {
        if (filter(node, this.options)) return rule;
      }
    }
    return null;
  };

  /**
   * Add a custom rule
   * @param {String} key - Unique key for the rule
   * @param {Object} rule - Rule definition
   * @returns {TurndownService} - The TurndownService instance
   */
  TurndownService.prototype.addRule = function (key, rule) {
    this.rules[key] = rule;
    return this;
  };

  /**
   * Mark elements to be removed
   * @param {String} selector - CSS selector for elements to remove
   * @returns {TurndownService} - The TurndownService instance
   */
  TurndownService.prototype.remove = function (selector) {
    this.rules[selector] = {
      filter: selector,
      replacement: function () { return '' }
    };
    return this;
  };

  /**
   * Mark elements to be kept in HTML form
   * @param {String} selector - CSS selector for elements to keep
   * @returns {TurndownService} - The TurndownService instance
   */
  TurndownService.prototype.keep = function (selector) {
    this.rules[selector] = {
      filter: selector,
      replacement: function (content, node) {
        return node.outerHTML;
      }
    };
    return this;
  };

  return TurndownService;
})();
