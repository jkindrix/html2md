/** Shared, side-effect-free conversion boundary helpers. */

function normalizeExtractedHtml(html) {
  if (typeof html !== 'string' || html.trim() === '') {
    throw new TypeError('Extracted HTML must be a non-empty string');
  }

  if (html.length < 100 || (!html.includes('<html') && !html.includes('<body'))) {
    return `<!DOCTYPE html><html><head><title>Document</title></head><body><div class="content">${html}</div></body></html>`;
  }

  return html;
}

const Grab2MdConversionUtils = Object.freeze({ normalizeExtractedHtml });

if (typeof globalThis !== 'undefined') {
  globalThis.Grab2MdConversionUtils = Grab2MdConversionUtils;
}

if (typeof module !== 'undefined') {
  module.exports = Grab2MdConversionUtils;
}
