/** Side-effect-free HTML-to-Markdown conversion controller. */

class Grab2MdConverter {
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
      linkStyle: 'inlined',
      codeBlockStyle: content.codeBlocks ? 'fenced' : 'indented'
    });

    if (!content.preserveImages) this.service.remove('img');
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
      replacement(contentValue, node, options) {
        const code = contentValue;
        if (options.codeBlockStyle !== 'fenced') {
          return `\n\n    ${code.replace(/\n/g, '\n    ')}\n\n`;
        }
        let language = '';
        for (const className of [node.className, node.firstChild?.className]) {
          const match = className && className.match(/language-(\w+)/);
          if (match) {
            language = match[1];
            break;
          }
        }
        const authoredFence = Math.max(
          0,
          ...[...code.matchAll(/`+/g)].map(match => match[0].length)
        );
        const fence = '`'.repeat(Math.max(3, authoredFence + 1));
        const closingSeparator = code.endsWith('\n') ? '' : '\n';
        return `\n\n${fence}${language}\n${code}${closingSeparator}${fence}\n\n`;
      }
    });
  }

  convert(html) {
    if (!this.service) throw new Error('Converter is not configured');
    return this.service.turndown(html);
  }
}

globalThis.Grab2MdConverter = Grab2MdConverter;
if (typeof module !== 'undefined') module.exports = { Grab2MdConverter };
