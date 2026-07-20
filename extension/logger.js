/** Production-safe extension logger. Diagnostic output is disabled by default. */

const Grab2MdLogger = Object.freeze({
  debug() {},
  warn() {},
  error() {}
});

if (typeof globalThis !== 'undefined') {
  globalThis.Grab2MdLogger = Grab2MdLogger;
}

if (typeof module !== 'undefined') {
  module.exports = Grab2MdLogger;
}
