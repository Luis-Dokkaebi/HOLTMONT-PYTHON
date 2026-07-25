/**
 * ======================================================================
 * MOCKS DE GOOGLE APPS SCRIPT PARA PRUEBAS LOCALES DE CODIGO.js
 * ======================================================================
 * Implementa en memoria los servicios que CODIGO.js necesita:
 *   SpreadsheetApp, LockService, PropertiesService, CacheService,
 *   Utilities, UrlFetchApp, HtmlService, DriveApp, Session.
 *
 * Uso:
 *   const { createEnv } = require('./gas_mocks');
 *   const env = createEnv({ 'HOJA': [[...], [...]] });
 *   env.api.apiSaveTrackerBatch('HOJA', [...], 'USUARIO');
 *
 * Ver AGENTS.md §6 "Mocking Local".
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const CODIGO_PATH = path.resolve(__dirname, '..', '..', 'CODIGO.js');

// ----------------------------------------------------------------------
// Range
// ----------------------------------------------------------------------
class MockRange {
  constructor(sheet, row, col, numRows, numCols) {
    this.sheet = sheet;
    this.row = row;
    this.col = col;
    this.numRows = numRows;
    this.numCols = numCols;
  }
  getRow() { return this.row; }
  getColumn() { return this.col; }
  getNumRows() { return this.numRows; }
  getNumColumns() { return this.numCols; }
  getValues() {
    this.sheet._ensure(this.row + this.numRows - 1, this.col + this.numCols - 1);
    const out = [];
    for (let r = 0; r < this.numRows; r++) {
      const src = this.sheet.values[this.row - 1 + r] || [];
      const line = [];
      for (let c = 0; c < this.numCols; c++) {
        const v = src[this.col - 1 + c];
        line.push(v === undefined ? "" : v);
      }
      out.push(line);
    }
    return out;
  }
  setValues(vals) {
    if (vals.length !== this.numRows) {
      throw new Error(`setValues: filas esperadas ${this.numRows}, recibidas ${vals.length}`);
    }
    vals.forEach(r => {
      if (r.length !== this.numCols) {
        throw new Error(`setValues: columnas esperadas ${this.numCols}, recibidas ${r.length}`);
      }
    });
    this.sheet._ensure(this.row + this.numRows - 1, this.col + this.numCols - 1);
    for (let r = 0; r < this.numRows; r++) {
      for (let c = 0; c < this.numCols; c++) {
        this.sheet.values[this.row - 1 + r][this.col - 1 + c] = vals[r][c];
      }
    }
    return this;
  }
  setValue(v) { return this.setValues([[v]]); }
  getValue() { return this.getValues()[0][0]; }
  setBackground() { return this; }
  setFontColor() { return this; }
  setNumberFormat() { return this; }
  clearContent() {
    for (let r = 0; r < this.numRows; r++) {
      for (let c = 0; c < this.numCols; c++) {
        if (this.sheet.values[this.row - 1 + r]) this.sheet.values[this.row - 1 + r][this.col - 1 + c] = "";
      }
    }
    return this;
  }
}

// ----------------------------------------------------------------------
// Sheet
// ----------------------------------------------------------------------
class MockSheet {
  constructor(name, values) {
    this.name = name;
    this.values = (values || []).map(r => r.slice());
    this.rules = [];
    this.filter = null;
    this.maxRows = Math.max(this.values.length, 200);
  }
  _width() {
    return this.values.reduce((m, r) => Math.max(m, r.length), 1);
  }
  _ensure(rows, cols) {
    const width = Math.max(cols, this._width());
    while (this.values.length < rows) this.values.push([]);
    this.values.forEach(r => { while (r.length < width) r.push(""); });
    this.maxRows = Math.max(this.maxRows, this.values.length);
  }
  getName() { return this.name; }
  getLastRow() {
    let last = 0;
    this.values.forEach((r, i) => {
      if (r.some(c => c !== "" && c !== null && c !== undefined)) last = i + 1;
    });
    return last;
  }
  getLastColumn() {
    let last = 0;
    this.values.forEach(r => r.forEach((c, j) => {
      if (c !== "" && c !== null && c !== undefined) last = Math.max(last, j + 1);
    }));
    return last;
  }
  getMaxRows() { return Math.max(this.maxRows, this.values.length); }
  getMaxColumns() { return Math.max(this._width(), 12); }
  getRange(row, col, numRows, numCols) {
    if (numRows === undefined) numRows = 1;
    if (numCols === undefined) numCols = 1;
    return new MockRange(this, row, col, numRows, numCols);
  }
  getDataRange() {
    return this.getRange(1, 1, Math.max(this.getLastRow(), 1), Math.max(this.getLastColumn(), 1));
  }
  getFilter() { return this.filter; }
  insertRowsBefore(pos, n) {
    const width = this._width();
    const blanks = [];
    for (let i = 0; i < n; i++) blanks.push(new Array(width).fill(""));
    this.values.splice(pos - 1, 0, ...blanks);
    this.maxRows += n;
  }
  deleteRow(pos) { this.values.splice(pos - 1, 1); }
  clearContents() { this.values = this.values.map(r => r.map(() => "")); }
  getConditionalFormatRules() { return this.rules.slice(); }
  setConditionalFormatRules(rules) { this.rules = rules.slice(); }
  appendRow(row) { this.values.push(row.slice()); }
  setFrozenRows() { return this; }
  autoResizeColumn() { return this; }
  hideColumns() { return this; }
  getSheetId() { return this.name.length; }
}

// ----------------------------------------------------------------------
// Spreadsheet
// ----------------------------------------------------------------------
class MockSpreadsheet {
  constructor() { this.sheets = []; }
  getSheetByName(n) { return this.sheets.find(s => s.getName() === n) || null; }
  getSheets() { return this.sheets.slice(); }
  insertSheet(n) { const s = new MockSheet(n, []); this.sheets.push(s); return s; }
  getSpreadsheetTimeZone() { return 'America/Monterrey'; }
  getName() { return 'HOLTMONT_MOCK'; }
  getId() { return 'MOCK_ID'; }
  toast() { }
}

// ----------------------------------------------------------------------
// Conditional format rule builder
// ----------------------------------------------------------------------
function newRuleBuilder() {
  const state = { formula: "", background: null, fontColor: null, ranges: [] };
  const builder = {
    whenFormulaSatisfied(f) { state.formula = f; return builder; },
    setBackground(b) { state.background = b; return builder; },
    setFontColor(c) { state.fontColor = c; return builder; },
    setRanges(r) { state.ranges = r; return builder; },
    build() {
      return {
        getBooleanCondition: () => ({
          getCriteriaType: () => 'CUSTOM_FORMULA',
          getCriteriaValues: () => [state.formula]
        }),
        getBackground: () => state.background,
        getFontColor: () => state.fontColor,
        getRanges: () => state.ranges,
        _formula: state.formula,
        _background: state.background
      };
    }
  };
  return builder;
}

// ----------------------------------------------------------------------
// Utilities.formatDate (soporta los patrones usados en CODIGO.js)
// ----------------------------------------------------------------------
function formatDate(date, tz, fmt) {
  const d = (date instanceof Date) ? date : new Date(date);
  const pad = (n) => String(n).padStart(2, '0');
  return fmt
    .replace(/yyyy/g, d.getFullYear())
    .replace(/yy/g, String(d.getFullYear()).slice(-2))
    .replace(/MM/g, pad(d.getMonth() + 1))
    .replace(/dd/g, pad(d.getDate()))
    .replace(/HH/g, pad(d.getHours()))
    .replace(/mm/g, pad(d.getMinutes()))
    .replace(/ss/g, pad(d.getSeconds()));
}

// ----------------------------------------------------------------------
// createEnv
// ----------------------------------------------------------------------
/**
 * @param {Object<string, Array<Array<*>>>} sheets  nombre -> matriz de valores
 * @returns {{api: Object, ss: MockSpreadsheet, spy: Object}}
 */
function createEnv(sheets) {
  const ss = new MockSpreadsheet();
  Object.entries(sheets || {}).forEach(([name, values]) => {
    ss.sheets.push(new MockSheet(name, values));
  });

  const spy = {
    cacheCalls: [],       // evidencia del Gatekeeper por _tempId (AGENTS.md §2)
    lockCalls: 0,
    urlFetchCalls: [],    // evidencia de webhooks (Make.com / Outlook)
    logs: []
  };

  const scriptProps = new Map();
  const cache = new Map();

  const SpreadsheetApp = {
    getActiveSpreadsheet: () => ss,
    getActive: () => ss,
    openById: () => ss,
    flush: () => { },
    BooleanCriteria: { CUSTOM_FORMULA: 'CUSTOM_FORMULA' },
    newConditionalFormatRule: () => newRuleBuilder(),
    getUi: () => ({
      alert: (msg) => { spy.logs.push(['UI_ALERT', msg]); },
      createMenu: () => ({ addItem: function () { return this; }, addSeparator: function () { return this; }, addToUi: () => { } }),
      prompt: () => ({ getSelectedButton: () => 'CANCEL', getResponseText: () => '' }),
      ButtonSet: { OK: 'OK', YES_NO: 'YES_NO' },
      Button: { OK: 'OK', YES: 'YES', CANCEL: 'CANCEL' }
    })
  };

  const LockService = {
    getScriptLock: () => ({
      tryLock: () => { spy.lockCalls++; return true; },
      waitLock: () => { spy.lockCalls++; return true; },
      releaseLock: () => { },
      hasLock: () => true
    })
  };

  const PropertiesService = {
    getScriptProperties: () => ({
      getProperty: (k) => (scriptProps.has(k) ? scriptProps.get(k) : null),
      setProperty: (k, v) => { scriptProps.set(k, String(v)); },
      deleteProperty: (k) => { scriptProps.delete(k); },
      getProperties: () => Object.fromEntries(scriptProps)
    }),
    getUserProperties: () => PropertiesService.getScriptProperties(),
    getDocumentProperties: () => PropertiesService.getScriptProperties()
  };

  const CacheService = {
    getScriptCache: () => ({
      get: (k) => { spy.cacheCalls.push(['get', k]); return cache.has(k) ? cache.get(k) : null; },
      put: (k, v, t) => { spy.cacheCalls.push(['put', k, v, t]); cache.set(k, String(v)); },
      remove: (k) => { spy.cacheCalls.push(['remove', k]); cache.delete(k); }
    }),
    getUserCache: () => CacheService.getScriptCache(),
    getDocumentCache: () => CacheService.getScriptCache()
  };

  const Utilities = {
    formatDate,
    sleep: () => { },
    getUuid: () => 'mock-uuid-' + Math.random().toString(36).slice(2),
    base64Decode: (s) => Buffer.from(String(s), 'base64'),
    base64Encode: (s) => Buffer.from(String(s)).toString('base64'),
    newBlob: (data, type, name) => ({ getBytes: () => data, getName: () => name, setName: () => { }, getContentType: () => type })
  };

  const UrlFetchApp = {
    fetch: (url, params) => {
      spy.urlFetchCalls.push({ url, params });
      return {
        getContentText: () => JSON.stringify({ candidates: [{ content: { parts: [{ text: 'MOCK' }] } }] }),
        getResponseCode: () => 200
      };
    }
  };

  const sandbox = {
    SpreadsheetApp, LockService, PropertiesService, CacheService,
    Utilities, UrlFetchApp,
    HtmlService: {
      createTemplateFromFile: () => ({ evaluate: () => ({ setTitle: function () { return this; }, addMetaTag: function () { return this; }, setXFrameOptionsMode: function () { return this; } }) }),
      createHtmlOutputFromFile: () => ({ getContent: () => '' }),
      XFrameOptionsMode: { ALLOWALL: 'ALLOWALL' }
    },
    DriveApp: {
      getFolderById: () => ({
        createFile: () => ({ getUrl: () => 'http://mock/file', setSharing: () => { }, getId: () => 'fid' }),
        getFolders: () => ({ hasNext: () => false }),
        getFiles: () => ({ hasNext: () => false })
      }),
      getRootFolder: () => ({ createFolder: () => ({ getId: () => 'fid' }) }),
      Access: { ANYONE_WITH_LINK: 'ANYONE_WITH_LINK' },
      Permission: { VIEW: 'VIEW' }
    },
    Session: {
      getActiveUser: () => ({ getEmail: () => 'mock@holtmont.com' }),
      getScriptTimeZone: () => 'America/Monterrey'
    },
    MailApp: { sendEmail: (o) => spy.logs.push(['MAIL', o]) },
    ScriptApp: {
      newTrigger: () => ({ timeBased: () => ({ everyDays: () => ({ atHour: () => ({ create: () => { } }) }) }), forSpreadsheet: () => ({ onEdit: () => ({ create: () => { } }) }) }),
      getProjectTriggers: () => [],
      deleteTrigger: () => { }
    },
    console,
    JSON, Math, Date, String, Number, Array, Object, parseInt, parseFloat, isNaN, RegExp, Error
  };
  sandbox.globalThis = sandbox;

  const context = vm.createContext(sandbox);
  const source = fs.readFileSync(CODIGO_PATH, 'utf8');
  vm.runInContext(source, context, { filename: 'CODIGO.js' });

  return { api: context, ss, spy, scriptProps, cache };
}

/** Devuelve la matriz cruda de una hoja del entorno. */
function sheetValues(env, name) {
  const s = env.ss.getSheetByName(name);
  return s ? s.values.map(r => r.slice()) : null;
}

/** Cuenta cuántas filas de una hoja contienen un texto dado (case-insensitive). */
function countRowsContaining(env, sheetName, text) {
  const vals = sheetValues(env, sheetName) || [];
  const needle = String(text).toUpperCase();
  return vals.filter(r => r.join('|').toUpperCase().includes(needle)).length;
}

module.exports = { createEnv, sheetValues, countRowsContaining, MockSheet, MockSpreadsheet, CODIGO_PATH };
