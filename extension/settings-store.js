/** Persistence adapter for popup settings. */

class Grab2MdSettingsStore {
  constructor(storage, key = 'grab2mdSettings') {
    this.storage = storage;
    this.key = key;
  }

  load(defaults, callback) {
    this.storage.get(this.key, data => {
      const saved = data[this.key] || {};
      callback({
        ...defaults,
        ...saved,
        markdownOptions: {
          ...defaults.markdownOptions,
          ...(saved.markdownOptions || {})
        },
        contentOptions: {
          ...defaults.contentOptions,
          ...(saved.contentOptions || {})
        }
      });
    });
  }

  save(settings, callback) {
    this.storage.set({ [this.key]: settings }, callback);
  }
}

globalThis.Grab2MdSettingsStore = Grab2MdSettingsStore;
if (typeof module !== 'undefined') module.exports = { Grab2MdSettingsStore };
