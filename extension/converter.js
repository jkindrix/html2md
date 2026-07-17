/** Side-effect-free HTML-to-Markdown conversion controller. */

class Html2MdConverter {
  constructor(Turndown = globalThis.TurndownService) {
    if (typeof Turndown !== 'function') {
      throw new TypeError('TurndownService is required');
    }
    this.Turndown = Turndown;
    this.service = null;
  }

  configure(settings) {
    const markdown = settings.markdownOptions;
    const content = settings.contentOptions;
    this.service = new this.Turndown({
      headingStyle: markdown.headingStyle,
      bulletListMarker: markdown.bulletMarker,
      linkStyle: markdown.linkStyle,
      codeBlockStyle: content.codeBlocks ? 'fenced' : 'indented'
    });

    if (!content.preserveImages) this.service.remove('img');
    if (content.includeTables) {
      this.service.keep(['table', 'tr', 'td', 'th', 'thead', 'tbody']);
    }
    this.service.addRule('codeBlock', {
      filter(node) {
        return (
          (node.nodeName === 'PRE' && node.firstChild?.nodeName === 'CODE') ||
          (node.nodeName === 'DIV' && node.classList && (
            node.classList.contains('code-block') ||
            node.classList.contains('whitespace-pre') ||
            node.classList.contains('bg-black')
          ))
        );
      },
      replacement(contentValue, node) {
        let language = '';
        for (const className of [node.className, node.firstChild?.className]) {
          const match = className && className.match(/language-(\w+)/);
          if (match) {
            language = match[1];
            break;
          }
        }
        return `\n\n\`\`\`${language}\n${contentValue.trim()}\n\`\`\`\n\n`;
      }
    });
  }

  convert(html) {
    if (!this.service) throw new Error('Converter is not configured');
    return this.service.turndown(html);
  }
}

globalThis.Html2MdConverter = Html2MdConverter;
if (typeof module !== 'undefined') module.exports = { Html2MdConverter };

