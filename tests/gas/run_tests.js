/**
 * ======================================================================
 * SUITE DE PRUEBAS UNITARIAS E INTEGRACIÓN — MIGRACIÓN HOLTMONT
 * ======================================================================
 * Ejecuta, contra el código real de CODIGO.js (cargado con mocks de GAS),
 * los 6 bloques del plan de pruebas:
 *   1. Semáforo (formato condicional) por CLASIFICACION
 *   2. Permisos de ruteo y tablas (VENTAS) — "La Ley de Antonia"
 *   3. Folios y prefijos personalizados
 *   4. Gatekeeper, duplicidad y auto-archivado
 *   5. Distribución lateral (Papa Caliente) y Reverse Sync
 *   6. Agente de métricas (KPIs / Gemini / Webhook Make.com)
 * + 7. Contrato frontend (index.html) ↔ backend (CODIGO.js)
 *
 * Uso:  node tests/gas/run_tests.js
 * Salida: tabla en consola + tests/gas/RESULTADOS.md
 * Código de salida: 0 si todo pasa, 1 si hay fallos.
 */

const fs = require('fs');
const path = require('path');
const { createEnv, countRowsContaining, sheetValues, CODIGO_PATH } = require('./gas_mocks');
const { resolveColor, COLOR_NAME } = require('./formula_eval');

const CODIGO_SRC = fs.readFileSync(CODIGO_PATH, 'utf8');
const INDEX_HTML = fs.readFileSync(path.resolve(__dirname, '..', '..', 'index.html'), 'utf8');

// ----------------------------------------------------------------------
// Framework mínimo
// ----------------------------------------------------------------------
const results = [];
let currentSection = '';

function section(name) { currentSection = name; }

function check(id, nombre, esperado, obtenido, ok, nota) {
  results.push({ seccion: currentSection, id, nombre, esperado: String(esperado), obtenido: String(obtenido), ok: !!ok, nota: nota || '' });
}

function run(id, nombre, fn) {
  try {
    fn();
  } catch (e) {
    check(id, nombre, 'ejecución sin excepción', 'EXCEPCIÓN: ' + e.message, false);
  }
}

// ----------------------------------------------------------------------
// Fixtures
// ----------------------------------------------------------------------
const TRACKER_HEADERS = ['ID', 'ESPECIALIDAD', 'CONCEPTO', 'FECHA', 'RELOJ', 'AVANCE', 'ESTATUS',
  'COMENTARIOS', 'ARCHIVO', 'CLASIFICACION', 'PRIORIDAD', 'FECHA_RESPUESTA', 'RESPONSABLE', 'CUMPLIMIENTO'];

const SALES_HEADERS = ['FOLIO', 'CLIENTE', 'CONCEPTO', 'VENDEDOR', 'FECHA', 'ESTATUS', 'COMENTARIOS',
  'ARCHIVO', 'MONTO', 'F2', 'COTIZACION', 'TIMELINE', 'LAYOUT', 'AVANCE', 'MAP COT', 'PROCESO_LOG'];

/** Hoja de tracker personal con 2 filas de UI encima de los encabezados (caso real). */
function tracker(rows) {
  return [
    ['HOLTMONT — TRACKER PERSONAL', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    new Array(TRACKER_HEADERS.length).fill(''),
    TRACKER_HEADERS.slice(),
    ...(rows || []).map(r => {
      const line = new Array(TRACKER_HEADERS.length).fill('');
      Object.entries(r).forEach(([k, v]) => {
        const i = TRACKER_HEADERS.indexOf(k);
        if (i > -1) line[i] = v;
      });
      return line;
    })
  ];
}

function sales(rows) {
  return [
    ['TABLA DE VENTAS', '', '', '', '', '', '', '', '', '', '', '', '', '', '', ''],
    SALES_HEADERS.slice(),
    ...(rows || []).map(r => {
      const line = new Array(SALES_HEADERS.length).fill('');
      Object.entries(r).forEach(([k, v]) => {
        const i = SALES_HEADERS.indexOf(k);
        if (i > -1) line[i] = v;
      });
      return line;
    })
  ];
}

/** Lee una fila (como objeto) por coincidencia de texto en cualquier celda. */
function findRow(env, sheetName, text) {
  const vals = sheetValues(env, sheetName) || [];
  const hdrIdx = vals.findIndex(r => r.join('|').toUpperCase().includes('CONCEPTO'));
  if (hdrIdx === -1) return null;
  const headers = vals[hdrIdx].map(h => String(h).toUpperCase().trim());
  const needle = String(text).toUpperCase();
  for (let i = hdrIdx + 1; i < vals.length; i++) {
    if (vals[i].join('|').toUpperCase().includes(needle)) {
      const o = {};
      headers.forEach((h, j) => { if (h) o[h] = vals[i][j]; });
      o._raw = vals[i];
      o._index = i;
      return o;
    }
  }
  return null;
}

/** Índice de la fila separadora "TAREAS REALIZADAS" (-1 si no existe). */
function separatorIndex(env, sheetName) {
  const vals = sheetValues(env, sheetName) || [];
  return vals.findIndex(r => r.join('|').toUpperCase().includes('TAREAS REALIZADAS'));
}

/** ¿La fila que contiene `text` está archivada (debajo del separador)? */
function isArchived(env, sheetName, text) {
  const sep = separatorIndex(env, sheetName);
  const row = findRow(env, sheetName, text);
  if (!row) return null;
  return sep > -1 && row._index > sep;
}

const hoy = new Date();
const diasAtras = (n) => new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() - n);

// ======================================================================
// 1. SEMÁFORO (FORMATO CONDICIONAL)
// ======================================================================
section('1. Semáforo / Formato condicional');

function semaforoRules() {
  const env = createEnv({
    'EDUARDO MANZANARES': tracker([
      { ID: 'T-1', CONCEPTO: 'REVISION SISTEMA', FECHA: diasAtras(1), CLASIFICACION: 'A', ESTATUS: 'PENDIENTE' }
    ]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  const sheet = env.ss.getSheetByName('EDUARDO MANZANARES');
  const aplicado = env.api.applyTrafficLightToSheet(sheet);
  return { env, sheet, aplicado, rules: sheet.getConditionalFormatRules() };
}

run('1.0', 'applyTrafficLightToSheet habilita la hoja de tracker', () => {
  const { aplicado, rules } = semaforoRules();
  check('1.0', 'Formato condicional aplicado a hoja habilitada', 'true + reglas > 0',
    `${aplicado} + ${rules.length} reglas`, aplicado === true && rules.length > 0);
});

run('1.0b', 'Hojas excluidas (LOG_SISTEMA) no reciben semáforo', () => {
  const { env } = semaforoRules();
  const log = env.ss.getSheetByName('LOG_SISTEMA');
  const res = env.api.applyTrafficLightToSheet(log);
  check('1.0b', 'LOG_SISTEMA excluida del semáforo', 'false', String(res), res === false);
});

const CASOS_SEMAFORO = [
  ['1.1', 'A', 0, '#00FF00', 'hoy (0 días)'],
  ['1.1', 'A', 1, '#00FF00', '1 día'],
  ['1.1', 'A', 2, '#FFFF00', '2 días'],
  ['1.1', 'A', 4, '#FF0000', '4 días'],
  ['1.2', 'AA', 11, '#00FF00', '11 días'],
  ['1.2', 'AA', 13, '#FFFF00', '13 días'],
  ['1.2', 'AA', 16, '#FF0000', '16 días'],
  ['1.3', 'AAA', 24, '#00FF00', '24 días'],
  ['1.3', 'AAA', 27, '#FFFF00', '27 días'],
  ['1.3', 'AAA', 32, '#FF0000', '32 días']
];

run('1.x', 'Colores del semáforo por clasificación', () => {
  const { rules } = semaforoRules();
  CASOS_SEMAFORO.forEach(([id, clase, dias, esperado, etiqueta]) => {
    const color = resolveColor(rules, { clase, dias });
    check(id, `Clasificación ${clase} — ${etiqueta}`,
      COLOR_NAME[esperado], COLOR_NAME[color] || String(color), color === esperado);
  });
});

run('1.4', 'Límite SLA de AA declarado en el plan (14 días)', () => {
  const { rules } = semaforoRules();
  // El plan y el dashboard declaran AA = 14 días -> a los 15 está VENCIDO (rojo)
  const color15 = resolveColor(rules, { clase: 'AA', dias: 15 });
  check('1.4', 'AA a los 15 días (límite del plan = 14)', COLOR_NAME['#FF0000'],
    COLOR_NAME[color15] || String(color15), color15 === '#FF0000');
});

// ======================================================================
// 2. PERMISOS DE RUTEO / TABLAS (VENTAS) — "LA LEY DE ANTONIA"
// ======================================================================
section('2. Ruteo y tablas (VENTAS)');

function envVentas(extra) {
  return createEnv(Object.assign({
    'ANTONIA_VENTAS': sales([]),
    'EDUARDO MANZANARES (VENTAS)': sales([]),
    'EDUARDO MANZANARES': tracker([]),
    'ANTONIA PINEDA LOPEZ': tracker([]),
    'ADMINISTRADOR': tracker([]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  }, extra || {}));
}

run('2.1', 'ANTONIA_VENTAS manda tarea a un vendedor', () => {
  const env = envVentas();
  env.api.apiSaveTrackerBatch('ANTONIA_VENTAS', [{
    CONCEPTO: 'COTIZACION NAVE ACME', CLIENTE: 'ACME', VENDEDOR: 'EDUARDO MANZANARES (VENTAS)',
    FECHA: '01/07/26', ESTATUS: 'EN PROCESO'
  }], 'ANTONIA_VENTAS');

  const enVentas = countRowsContaining(env, 'EDUARDO MANZANARES (VENTAS)', 'COTIZACION NAVE ACME');
  check('2.1', 'La tarea llega a la hoja del vendedor con sufijo (VENTAS)', '1 fila', `${enVentas} fila(s)`, enVentas === 1);

  const folio = findRow(env, 'ANTONIA_VENTAS', 'COTIZACION NAVE ACME');
  check('2.1b', 'Antonia genera folio para la nueva cotización', 'folio no vacío',
    folio ? `FOLIO="${folio.FOLIO}"` : 'fila no encontrada', !!(folio && String(folio.FOLIO).trim()));
});

run('2.1c', 'El titular sí puede escribir en su propia tabla (VENTAS)', () => {
  const env = envVentas({ 'ANGEL SALINAS (VENTAS)': sales([]) });
  env.api.apiSaveTrackerBatch('ANGEL SALINAS (VENTAS)', [{
    CONCEPTO: 'COTIZACION PROPIA ANGEL', FECHA: '01/07/26', ESTATUS: 'EN PROCESO'
  }], 'ANGEL_SALINAS');
  const enVentas = countRowsContaining(env, 'ANGEL SALINAS (VENTAS)', 'COTIZACION PROPIA ANGEL');
  check('2.1c', 'El vendedor conserva su hoja (VENTAS) al guardar', '1 fila',
    `${enVentas} fila(s)`, enVentas === 1);
});

run('2.2', 'Otro usuario intenta mandar tarea a la hoja (VENTAS) de un vendedor', () => {
  const env = envVentas();
  env.api.apiSaveTrackerBatch('EDUARDO MANZANARES (VENTAS)', [{
    CONCEPTO: 'TAREA GENERAL DE LUIS', FECHA: '01/07/26', ESTATUS: 'PENDIENTE'
  }], 'LUIS_CARLOS');

  const enVentas = countRowsContaining(env, 'EDUARDO MANZANARES (VENTAS)', 'TAREA GENERAL DE LUIS');
  const enGeneral = countRowsContaining(env, 'EDUARDO MANZANARES', 'TAREA GENERAL DE LUIS');
  const enAntonia = countRowsContaining(env, 'ANTONIA_VENTAS', 'TAREA GENERAL DE LUIS');

  check('2.2a', 'El sufijo (VENTAS) se purga: escribe en el tracker general', '1 fila en "EDUARDO MANZANARES"',
    `${enGeneral} fila(s)`, enGeneral === 1);
  check('2.2b', 'NO se escribe en la tabla de ventas del vendedor', '0 filas en "(VENTAS)"',
    `${enVentas} fila(s)`, enVentas === 0);
  check('2.2c', 'NO contamina la maestra de Antonia (reverse sync indebido)', '0 filas en ANTONIA_VENTAS',
    `${enAntonia} fila(s)`, enAntonia === 0);
});

run('2.2d', 'Mismo caso vía apiUpdateTask / internalUpdateTask', () => {
  const env = envVentas();
  env.api.apiUpdateTask('EDUARDO MANZANARES (VENTAS)', {
    CONCEPTO: 'UPDATE DIRECTO LUIS', FECHA: '02/07/26'
  }, 'LUIS_CARLOS');
  const enVentas = countRowsContaining(env, 'EDUARDO MANZANARES (VENTAS)', 'UPDATE DIRECTO LUIS');
  const enGeneral = countRowsContaining(env, 'EDUARDO MANZANARES', 'UPDATE DIRECTO LUIS');
  check('2.2d', 'internalUpdateTask también purga el sufijo (VENTAS)',
    'general=1 / ventas=0', `general=${enGeneral} / ventas=${enVentas}`, enGeneral === 1 && enVentas === 0);
});

run('2.3', 'Usuario común intenta mandar tarea al core de ventas de Toñita', () => {
  const env = envVentas();
  env.api.apiSaveTrackerBatch('ANTONIA_VENTAS', [{
    CONCEPTO: 'TAREA GENERAL PARA TONITA', FECHA: '03/07/26', ESTATUS: 'PENDIENTE'
  }], 'EDUARDO_MANZANARES');

  const enCore = countRowsContaining(env, 'ANTONIA_VENTAS', 'TAREA GENERAL PARA TONITA');
  const enPersonal = countRowsContaining(env, 'ANTONIA PINEDA LOPEZ', 'TAREA GENERAL PARA TONITA');
  check('2.3a', 'Se redirige al tracker personal ANTONIA PINEDA LOPEZ', '1 fila en tracker personal',
    `${enPersonal} fila(s)`, enPersonal === 1);
  check('2.3b', 'NO se escribe en el core de ventas ANTONIA_VENTAS', '0 filas en ANTONIA_VENTAS',
    `${enCore} fila(s)`, enCore === 0);

  const row = findRow(env, 'ANTONIA PINEDA LOPEZ', 'TAREA GENERAL PARA TONITA')
    || findRow(env, 'ANTONIA_VENTAS', 'TAREA GENERAL PARA TONITA');
  const folio = row ? String(row.FOLIO || row.ID || '') : '';
  check('2.3c', 'El folio usa prefijo AP- (no AV-)', 'empieza con "AP-"',
    folio ? `"${folio}"` : 'sin folio', /^AP-/.test(folio));
});

// ======================================================================
// 3. FOLIOS Y PREFIJOS PERSONALIZADOS
// ======================================================================
section('3. Folios y prefijos');

run('3.0', 'Existencia de generatePrefix', () => {
  const existe = typeof (createEnv({}).api.generatePrefix) === 'function';
  check('3.0', 'La función generatePrefix está definida en CODIGO.js', 'function',
    existe ? 'function' : 'undefined', existe);
});

const CASOS_PREFIJO = [
  ['JAIME OLIVO', 'JAIME_OLIVO', 'JO-'],
  ['JESUS CANTU', 'JESUS_CANTU', 'JC-'],
  ['LUIS CARLOS', 'LUIS_CARLOS', 'LC-'],
  ['ADMINISTRADOR', 'ADMINISTRADOR', 'LC-'],
  ['ANTONIA_VENTAS', 'ANTONIA_VENTAS', 'AV-'],
  ['RAMIRO RODRIGUEZ', 'RAMIRO_RODRIGUEZ', 'RR-'],
  ['SEBASTIAN PADILLA', 'SEBASTIAN_PADILLA', 'SP-'],
  ['TERESA GARZA', 'TERESA_GARZA', 'TG-'],
  ['MIGUEL GALLARDO', 'MIGUEL_GALLARDO', 'MG-']   // 3.2 fallback dinámico
];

run('3.1', 'Prefijo de folio por usuario al crear tarea', () => {
  CASOS_PREFIJO.forEach(([hoja, usuario, prefijo]) => {
    const env = createEnv({
      [hoja]: hoja === 'ANTONIA_VENTAS' ? sales([]) : tracker([]),
      'ADMINISTRADOR': tracker([]),
      'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
    });
    env.api.apiSaveTrackerBatch(hoja, [{ CONCEPTO: 'TAREA NUEVA ' + usuario, FECHA: '05/07/26' }], usuario);
    const row = findRow(env, hoja, 'TAREA NUEVA ' + usuario);
    const folio = row ? String(row.FOLIO || row.ID || '') : '';
    check('3.1', `Folio de ${usuario} inicia con ${prefijo}`, prefijo + '…',
      folio ? `"${folio}"` : '(folio vacío)', folio.indexOf(prefijo) === 0);
  });
});

run('3.2', 'Fallback seguro PPC- cuando no hay nombre', () => {
  const api = createEnv({}).api;
  let valor;
  try { valor = typeof api.generatePrefix === 'function' ? api.generatePrefix('') : '(función inexistente)'; }
  catch (e) { valor = 'EXCEPCIÓN: ' + e.message; }
  check('3.2', 'generatePrefix("") retorna "PPC-"', 'PPC-', valor, valor === 'PPC-');
});

// ======================================================================
// 4. GATEKEEPER, DUPLICIDAD Y AUTO-ARCHIVADO
// ======================================================================
section('4. Gatekeeper / duplicidad / archivado');

run('4.1', 'Anti-duplicación backend con mismo _tempId', () => {
  const env = createEnv({
    'JAIME OLIVO': tracker([]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  const payload = { CONCEPTO: 'TAREA DOBLE CLICK', FECHA: '06/07/26', ESTATUS: 'PENDIENTE', _tempId: 'tmp_123456' };
  for (let i = 0; i < 5; i++) {
    env.api.apiSaveTrackerBatch('JAIME OLIVO', [JSON.parse(JSON.stringify(payload))], 'JAIME_OLIVO');
  }
  const filas = countRowsContaining(env, 'JAIME OLIVO', 'TAREA DOBLE CLICK');
  check('4.1a', '5 peticiones idénticas con el mismo _tempId insertan 1 sola fila', '1 fila',
    `${filas} fila(s)`, filas === 1);
  check('4.1b', 'El backend usa CacheService como Gatekeeper del _tempId (AGENTS.md §2)',
    'al menos 1 llamada a CacheService', `${env.spy.cacheCalls.length} llamadas`, env.spy.cacheCalls.length > 0);
  const usaTempId = /_tempId/.test(CODIGO_SRC);
  check('4.1c', 'CODIGO.js referencia _tempId', 'sí', usaTempId ? 'sí' : 'no (0 ocurrencias)', usaTempId);
});

run('4.1d', 'Protección frontend: bandera isSubmitting', () => {
  const ocurrencias = (INDEX_HTML.match(/isSubmitting/g) || []).length;
  check('4.1d', 'index.html implementa el flag reactivo isSubmitting', '> 0 ocurrencias',
    `${ocurrencias} ocurrencias`, ocurrencias > 0);
});

run('4.2', 'Fallback de recuperación de fila sin FOLIO (CONCEPTO+FECHA+RESPONSABLE)', () => {
  const env = createEnv({
    'JAIME OLIVO': tracker([
      { ID: '', CONCEPTO: 'REVISION DE PLANOS', FECHA: '10/07/26', RESPONSABLE: 'JAIME OLIVO', ESTATUS: 'PENDIENTE', COMENTARIOS: '' }
    ]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  env.api.apiUpdateTask('JAIME OLIVO', {
    CONCEPTO: 'REVISION DE PLANOS', FECHA: '10/07/26', RESPONSABLE: 'JAIME OLIVO',
    COMENTARIOS: 'COMENTARIO NUEVO DEL FRONTEND'
  }, 'JAIME_OLIVO');

  const filas = countRowsContaining(env, 'JAIME OLIVO', 'REVISION DE PLANOS');
  check('4.2a', 'No se duplica la tarea: se sobrescribe la fila existente', '1 fila',
    `${filas} fila(s)`, filas === 1);
  // La fila original es la que conserva ESTATUS "PENDIENTE"
  // (las filas nuevas creadas por el backend nacen con ESTATUS "ASIGNADO").
  const vals = sheetValues(env, 'JAIME OLIVO') || [];
  const iConcepto = TRACKER_HEADERS.indexOf('CONCEPTO');
  const iEstatus = TRACKER_HEADERS.indexOf('ESTATUS');
  const iComent = TRACKER_HEADERS.indexOf('COMENTARIOS');
  const original = vals.find(r => String(r[iConcepto]).toUpperCase() === 'REVISION DE PLANOS'
    && String(r[iEstatus]).toUpperCase() === 'PENDIENTE');
  const comentario = original ? String(original[iComent] || '') : '(fila original no encontrada)';
  check('4.2b', 'El comentario se escribe en la fila original (no en una copia)', 'COMENTARIO NUEVO DEL FRONTEND',
    comentario || '(vacío)', comentario === 'COMENTARIO NUEVO DEL FRONTEND');
});

run('4.3', 'Auto-archivado a TAREAS REALIZADAS', () => {
  const env = createEnv({
    'JAIME OLIVO': tracker([
      { ID: 'T-100', CONCEPTO: 'AVANCE NATIVO UNO', FECHA: '01/07/26', AVANCE: 1, ESTATUS: 'EN PROCESO' },
      { ID: 'T-101', CONCEPTO: 'AVANCE STRING CIEN', FECHA: '01/07/26', AVANCE: '100%', ESTATUS: 'EN PROCESO' },
      { ID: 'T-102', CONCEPTO: 'ESTATUS HECHO', FECHA: '01/07/26', AVANCE: '', ESTATUS: 'HECHO' },
      { ID: 'T-103', CONCEPTO: 'CUMPLIMIENTO SI', FECHA: '01/07/26', AVANCE: '', ESTATUS: 'EN PROCESO', CUMPLIMIENTO: 'SI' },
      { ID: 'T-104', CONCEPTO: 'AVANCE UNO POR CIENTO', FECHA: '01/07/26', AVANCE: '1', ESTATUS: 'EN PROCESO' },
      { ID: 'T-105', CONCEPTO: 'TAREA ACTIVA CONTROL', FECHA: '01/07/26', AVANCE: '40', ESTATUS: 'EN PROCESO' }
    ]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  env.api.apiSaveTrackerBatch('JAIME OLIVO', [{ ID: 'T-105', COMENTARIOS: 'PING' }], 'JAIME_OLIVO');

  check('4.3a', 'AVANCE nativo 1 (celda porcentaje) se archiva', 'archivada',
    isArchived(env, 'JAIME OLIVO', 'AVANCE NATIVO UNO') ? 'archivada' : 'activa',
    isArchived(env, 'JAIME OLIVO', 'AVANCE NATIVO UNO') === true);
  check('4.3b', 'AVANCE "100%" (string del frontend) se archiva', 'archivada',
    isArchived(env, 'JAIME OLIVO', 'AVANCE STRING CIEN') ? 'archivada' : 'activa',
    isArchived(env, 'JAIME OLIVO', 'AVANCE STRING CIEN') === true);
  check('4.3c', 'ESTATUS = HECHO archiva la tarea', 'archivada',
    isArchived(env, 'JAIME OLIVO', 'ESTATUS HECHO') ? 'archivada' : 'activa',
    isArchived(env, 'JAIME OLIVO', 'ESTATUS HECHO') === true);
  check('4.3d', 'CUMPLIMIENTO = SI archiva la tarea', 'archivada',
    isArchived(env, 'JAIME OLIVO', 'CUMPLIMIENTO SI') ? 'archivada' : 'activa',
    isArchived(env, 'JAIME OLIVO', 'CUMPLIMIENTO SI') === true);
  check('4.3e', 'AVANCE "1" (1 %) NO debe interpretarse como 100 % (AGENTS.md §4)', 'activa',
    isArchived(env, 'JAIME OLIVO', 'AVANCE UNO POR CIENTO') ? 'archivada' : 'activa',
    isArchived(env, 'JAIME OLIVO', 'AVANCE UNO POR CIENTO') === false);
  check('4.3f', 'Tarea con 40 % permanece activa (control)', 'activa',
    isArchived(env, 'JAIME OLIVO', 'TAREA ACTIVA CONTROL') ? 'archivada' : 'activa',
    isArchived(env, 'JAIME OLIVO', 'TAREA ACTIVA CONTROL') === false);
});

// ======================================================================
// 5. DISTRIBUCIÓN LATERAL (PAPA CALIENTE) Y REVERSE SYNC
// ======================================================================
section('5. Papa Caliente y Reverse Sync');

run('5.1', 'Delegación de la fase CD desde Toñita a ANGEL SALINAS', () => {
  const env = createEnv({
    'ANTONIA_VENTAS': sales([
      { FOLIO: 'AV-2025', CLIENTE: 'ACME', CONCEPTO: 'COTIZACION PLANTA', VENDEDOR: 'ANTONIA_VENTAS', FECHA: '01/07/26', ESTATUS: 'EN PROCESO', 'MAP COT': '⚪ CD', PROCESO_LOG: '[]' }
    ]),
    'ANGEL SALINAS': tracker([]),
    'ANGEL SALINAS (VENTAS)': sales([]),
    'ADMINISTRADOR': tracker([]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  env.api.apiUpdateTask('ANTONIA_VENTAS', {
    FOLIO: 'AV-2025', PROCESO: 'CD', INVOLUCRADOS: 'ANGEL SALINAS', 'MAP COT': '🔴 CD'
  }, 'ANTONIA_VENTAS');

  const enTracker = countRowsContaining(env, 'ANGEL SALINAS', 'COTIZACION PLANTA');
  const enVentasAngel = countRowsContaining(env, 'ANGEL SALINAS (VENTAS)', 'COTIZACION PLANTA');
  check('5.1a', 'Aparece la fase delegada en la hoja de ANGEL SALINAS', '1 fila (tracker o ventas)',
    `tracker=${enTracker} / ventas=${enVentasAngel}`, (enTracker + enVentasAngel) >= 1);

  const rowAngel = findRow(env, 'ANGEL SALINAS', 'COTIZACION PLANTA') || findRow(env, 'ANGEL SALINAS (VENTAS)', 'COTIZACION PLANTA');
  const marca = rowAngel ? String(rowAngel.CONCEPTO || '') : '';
  check('5.1b', 'El CONCEPTO delegado lleva la marca [Calculo y Diseño]', 'CONCEPTO … [Calculo y Diseño]',
    marca || '(sin fila)', /\[Calculo y Dise/i.test(marca));

  const rowAnt = findRow(env, 'ANTONIA_VENTAS', 'AV-2025');
  const mapcot = rowAnt ? String(rowAnt['MAP COT'] || '') : '';
  check('5.1c', 'MAP COT de la etapa CD pasa de ⚪ a 🔴', '🔴 CD', mapcot || '(vacío)', /🔴\s*CD/.test(mapcot));

  const backendPapaCaliente = /PROCESO_LOG/.test(CODIGO_SRC) || /MAP COT/.test(CODIGO_SRC);
  check('5.1d', 'CODIGO.js implementa la lógica PROCESO_LOG / MAP COT', 'sí',
    backendPapaCaliente ? 'sí' : 'no (0 ocurrencias en CODIGO.js)', backendPapaCaliente);
});

function envReverseSync() {
  const env = createEnv({
    'ANTONIA_VENTAS': sales([
      {
        FOLIO: 'AV-2025', CLIENTE: 'ACME', CONCEPTO: 'COTIZACION PLANTA', VENDEDOR: 'ANGEL SALINAS (VENTAS)',
        FECHA: '01/07/26', ESTATUS: 'EN PROCESO', AVANCE: '40', COTIZACION: '', 'MAP COT': '🔴 CD', PROCESO_LOG: '[]'
      }
    ]),
    'ANGEL SALINAS (VENTAS)': sales([
      {
        FOLIO: 'AV-2025', CLIENTE: 'ACME', CONCEPTO: 'COTIZACION PLANTA [Calculo y Diseño]',
        FECHA: '01/07/26', ESTATUS: 'EN PROCESO', AVANCE: '', COTIZACION: ''
      }
    ]),
    'ADMINISTRADOR': tracker([]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  env.api.apiSaveTrackerBatch('ANGEL SALINAS (VENTAS)', [{
    FOLIO: 'AV-2025', COTIZACION: 'https://drive.google.com/cot_2025.pdf',
    ARCHIVO: 'https://drive.google.com/plano.pdf', AVANCE: '100', ESTATUS: 'DONE'
  }], 'ANGEL_SALINAS');
  return env;
}

run('5.2', 'Reverse Sync del trabajador hacia Toñita', () => {
  const env = envReverseSync();
  const archivadaAngel = isArchived(env, 'ANGEL SALINAS (VENTAS)', 'COTIZACION PLANTA');
  check('5.2a', 'La tarea se archiva en la hoja de ANGEL SALINAS', 'archivada',
    archivadaAngel ? 'archivada' : 'activa', archivadaAngel === true);

  const rowAnt = findRow(env, 'ANTONIA_VENTAS', 'AV-2025');
  const cot = rowAnt ? String(rowAnt.COTIZACION || '') : '';
  check('5.2b', 'La COTIZACION se inserta en la celda correcta de ANTONIA_VENTAS', 'URL del archivo',
    cot || '(vacío)', cot.includes('cot_2025.pdf'));

  const log = rowAnt ? String(rowAnt.PROCESO_LOG || '') : '';
  check('5.2c', 'PROCESO_LOG de Antonia marca la etapa como DONE', 'contiene DONE',
    log || '(vacío)', /DONE/i.test(log));

  const mapcot = rowAnt ? String(rowAnt['MAP COT'] || '') : '';
  check('5.2d', 'MAP COT de CD cambia a 🟢', '🟢 CD', mapcot || '(vacío)', /🟢\s*CD/.test(mapcot));
});

run('5.3', 'Prevención de cierre prematuro de la venta global', () => {
  const env = envReverseSync();
  const rowAnt = findRow(env, 'ANTONIA_VENTAS', 'AV-2025');
  const estatus = rowAnt ? String(rowAnt.ESTATUS || '') : '(fila no encontrada)';
  const avance = rowAnt ? String(rowAnt.AVANCE || '') : '(fila no encontrada)';
  check('5.3a', 'El ESTATUS de Antonia NO se sobrescribe con el del trabajador', 'EN PROCESO',
    estatus, estatus.toUpperCase() === 'EN PROCESO');
  check('5.3b', 'El AVANCE de Antonia NO se sobrescribe con 100', '40', avance, avance === '40');
  const archivadaAntonia = isArchived(env, 'ANTONIA_VENTAS', 'AV-2025');
  check('5.3c', 'La cotización de Antonia NO se auto-archiva por el avance del trabajador', 'activa',
    archivadaAntonia ? 'archivada (venta cerrada)' : 'activa', archivadaAntonia === false);
});

// ======================================================================
// 6. AGENTE DE MÉTRICAS (KPIs / GEMINI / WEBHOOK)
// ======================================================================
section('6. Métricas, Gemini y Webhook');

run('6.1', 'Agente de métricas de cotizaciones', () => {
  const api = createEnv({ 'ANTONIA_VENTAS': sales([]) }).api;
  [['runQuoteMetricsAgent', '6.1a'], ['autoUpdateQuoteMetrics', '6.1b'], ['apiFetchQuoteAgentMetrics', '6.1c']]
    .forEach(([fn, id]) => {
      const t = typeof api[fn];
      check(id, `${fn} está definida en CODIGO.js`, 'function', t, t === 'function');
    });
});

run('6.2', 'Contexto de integración con Gemini para el reporte', () => {
  const api = createEnv({}).api;
  const tieneKeyApi = typeof api.apiSaveGeminiKey === 'function' && typeof api.apiCheckGeminiKey === 'function';
  check('6.2a', 'API de configuración de GEMINI_API_KEY (apiSaveGeminiKey/apiCheckGeminiKey)', 'function',
    tieneKeyApi ? 'function' : 'undefined', tieneKeyApi);
  const tienePrompt = /recomendaci[oó]n operativa/i.test(CODIGO_SRC);
  check('6.2b', 'Prompt de métricas con "recomendación operativa"', 'presente en CODIGO.js',
    tienePrompt ? 'presente' : 'ausente', tienePrompt);
  const tieneReporte = typeof api.apiGetLastAgentReport === 'function';
  check('6.2c', 'apiGetLastAgentReport (resumen de ~180 palabras al dashboard)', 'function',
    tieneReporte ? 'function' : 'undefined', tieneReporte);
});

run('6.3', 'Webhook Make.com / Outlook', () => {
  const env = createEnv({
    'JEHU MARTINEZ': tracker([]),
    'ADMINISTRADOR': tracker([]),
    'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']]
  });
  env.api.apiSaveTrackerBatch('JEHU MARTINEZ', [{
    CONCEPTO: 'NUEVA ASIGNACION', FECHA: '07/07/26', RESPONSABLE: 'JEHU MARTINEZ', ESTATUS: 'ASIGNADO'
  }], 'LUIS_CARLOS');

  check('6.3a', 'Se dispara el webhook al asignar un nuevo RESPONSABLE', '≥ 1 llamada UrlFetchApp',
    `${env.spy.urlFetchCalls.length} llamadas`, env.spy.urlFetchCalls.length >= 1);

  const tieneNotifier = /NotifierService|sendToOutlook|hook\.(eu|us)\d*\.make\.com|make\.com/i.test(CODIGO_SRC);
  check('6.3b', 'CODIGO.js contiene el NotifierService / endpoint de Make.com', 'presente',
    tieneNotifier ? 'presente' : 'ausente', tieneNotifier);

  const tieneIso = /toISOString\(\)/.test(CODIGO_SRC);
  check('6.3c', 'La fecha del payload usa .toISOString() (AGENTS.md §5)', 'presente',
    tieneIso ? 'presente' : 'ausente (0 ocurrencias)', tieneIso);

  const emails = (CODIGO_SRC.match(/@holtmont\.com/g) || []).length;
  check('6.3d', 'USER_DB mapea correos corporativos @holtmont.com', '> 0 correos',
    `${emails} correos`, emails > 0);
});

// ======================================================================
// 7. CONTRATO FRONTEND ↔ BACKEND (verificación de integración)
// ======================================================================
section('7. Contrato index.html ↔ CODIGO.js');

run('7.1', 'Todas las funciones invocadas por el frontend existen en el backend', () => {
  const definidas = new Set([...CODIGO_SRC.matchAll(/^function\s+([A-Za-z0-9_]+)\s*\(/gm)].map(m => m[1]));
  const llamadas = new Set([...INDEX_HTML.matchAll(/\.\s*((?:api|run)[A-Za-z0-9_]*)\s*\(/g)].map(m => m[1]));
  const faltantes = [...llamadas].filter(c => !definidas.has(c)).sort();
  check('7.1', 'Funciones google.script.run sin implementación en CODIGO.js', '0 faltantes',
    faltantes.length ? `${faltantes.length}: ${faltantes.join(', ')}` : '0 faltantes', faltantes.length === 0);
});

run('7.1b', 'Adaptador de migración (api_service.js): métodos críticos implementados', () => {
  const adapter = fs.readFileSync(path.resolve(__dirname, '..', '..', 'api_service.js'), 'utf8');
  const criticos = ['apiSaveTrackerBatch', 'apiUpdateTask', 'apiUpdatePPCV3', 'apiFetchWeeklyPlanData', 'apiFetchSalesHistory'];
  const stubs = criticos.filter(m => {
    const re = new RegExp(`${m}\\s*\\([^)]*\\)\\s*\\{([\\s\\S]*?)\\n    \\}`);
    const body = (re.exec(adapter) || [])[1] || '';
    const llamaBackend = /fetch\(|this\._post\(|this\._call\(/.test(body);
    return /not implemented|stub/i.test(body) || !llamaBackend;
  });
  check('7.1b', 'Métodos de guardado del adaptador FastAPI que siguen siendo stubs', '0 stubs',
    stubs.length ? `${stubs.length}: ${stubs.join(', ')}` : '0 stubs', stubs.length === 0,
    'Un stub responde {success:true} sin persistir nada en Supabase/FastAPI');
});

run('7.2', 'apiSaveTrackerBatch devuelve res.data para fusionar en el frontend (AGENTS.md §2)', () => {
  const env = createEnv({ 'JAIME OLIVO': tracker([]), 'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']] });
  const res = env.api.apiSaveTrackerBatch('JAIME OLIVO', [{ CONCEPTO: 'X', FECHA: '08/07/26', _tempId: 't1' }], 'JAIME_OLIVO');
  const tieneData = !!(res && res.data);
  check('7.2', 'La respuesta incluye res.data con la tarea actualizada', 'res.data presente',
    tieneData ? 'presente' : `ausente (${JSON.stringify(res)})`, tieneData);
});

// ======================================================================
// 8. SUPABASE SYNC (escritura doble Sheets -> Postgres)
// ======================================================================
section('8. Supabase Sync (escritura doble)');

/** Entorno con SupabaseSync configurado y las peticiones capturadas. */
function envSupabase(sheets, opciones) {
  const cfg = opciones || {};
  const peticiones = [];
  const env = createEnv(sheets, {
    fetchHandler: (url, params) => {
      peticiones.push({ url, params });
      if (cfg.lanzar) throw new Error('red caída');
      if (url.indexOf('/people?') >= 0) {
        return { code: 200, text: JSON.stringify(cfg.people || []) };
      }
      return { code: cfg.code === undefined ? 201 : cfg.code, text: '' };
    }
  });
  if (!cfg.sinConfigurar) {
    env.scriptProps.set('SUPABASE_URL', 'https://proyecto.supabase.co');
    env.scriptProps.set('SUPABASE_KEY', 'clave-de-prueba');
  }
  env.peticiones = peticiones;
  return env;
}

/** Peticiones dirigidas a una tabla concreta (ignora el lookup de people). */
function peticionesA(env, tabla) {
  return env.peticiones.filter(p => p.url.indexOf('/rest/v1/' + tabla) >= 0);
}

run('8.1', 'computeDedupeKey: paridad con los 4,626 registros migrados', () => {
  const env = envSupabase({});
  const S = env.api.SupabaseSync;
  const casos = [
    // [folio, hoja, esperado, por qué]
    ['PPC-301831732', 'ADMINISTRADOR', 'PPC-301831732', 'secuencia global'],
    ['AV-0042', 'ANTONIA_VENTAS', 'AV-0042', 'secuencia global de ventas'],
    ['TG-0003', 'TERESA GARZA', 'TG-0003', 'secuencia global'],
    ['1772639658256', 'ADMINISTRADOR', '1772639658256', 'id tipo timestamp'],
    ['1772639658256.0', 'ADMINISTRADOR', '1772639658256.0', 'timestamp con .0 de Sheets'],
    // Los folios con iniciales de persona NO son globales.
    ['JO-0009', 'JAIME OLIVO', 'JAIME OLIVO::JO-0009', 'inicial de persona -> local'],
    ['SP-0007', 'ADMINISTRADOR', 'ADMINISTRADOR::SP-0007', 'inicial de persona -> local'],
    ['JO-513177087', 'ADMINISTRADOR', 'ADMINISTRADOR::JO-513177087', 'inicial + digitos -> local'],
    ['1308.0', 'ADMINISTRADOR', 'ADMINISTRADOR::1308.0', 'numerico corto -> local'],
    ['ADMINISTRADOR::ROW1604', 'ADMINISTRADOR', 'ADMINISTRADOR::ROW1604', 'folio sintetico intacto'],
    // Hoja real con espacio inicial: la clave migrada lo conserva. Recortarlo
    // generaria una clave distinta y el upsert duplicaria la fila.
    ['LM-1940', ' LILIANA AYLIN MARTINEZ IBARRA', ' LILIANA AYLIN MARTINEZ IBARRA::LM-1940', 'espacio inicial preservado']
  ];
  const fallos = casos.filter(c => S.computeDedupeKey(c[0], c[1]) !== c[2])
                      .map(c => `${c[0]}@${c[1]} -> ${S.computeDedupeKey(c[0], c[1])} (esperado ${c[2]})`);
  check('8.1', 'Clave de identidad de fila para los 10 casos reales', '0 fallos',
    fallos.length ? fallos.join(' | ') : '0 fallos', fallos.length === 0,
    'JO-0009 vive en 10 trackers: cada copia necesita su propia clave');
});

run('8.2', 'El mismo folio difundido a varias hojas produce claves distintas', () => {
  const env = envSupabase({});
  const S = env.api.SupabaseSync;
  const hojas = ['JAIME OLIVO', 'TERESA GARZA', 'RAMIRO RODRIGUEZ'];
  const claves = hojas.map(h => S.computeDedupeKey('JO-0009', h));
  const unicas = new Set(claves).size === claves.length;
  check('8.2', 'Papa Caliente: JO-0009 no se colapsa en una sola fila', '3 claves distintas',
    `${new Set(claves).size} distintas`, unicas);
});

run('8.3', 'normalizeAvance respeta AGENTS.md §4', () => {
  const env = envSupabase({});
  const S = env.api.SupabaseSync;
  const casos = [
    [1, 100, 'numero 1 = celda con formato % = 100%'],
    ['1', 1, 'string "1" lo tecleo una persona = 1%'],
    ['1.0', 1, 'string "1.0" tambien es 1%'],
    [0.5, 50, 'numero 0.5 = 50%'],
    [100, 100, 'ya en escala 0-100'],
    ['100%', 100, 'texto con %'],
    ['0%', 0, 'cero textual'],
    [0, 0, 'cero numerico'],
    ['', null, 'vacio -> null'],
    ['N/A', null, 'no numerico -> null']
  ];
  const fallos = casos.filter(c => S.normalizeAvance(c[0]) !== c[1])
                      .map(c => `${JSON.stringify(c[0])} -> ${S.normalizeAvance(c[0])} (esperado ${c[1]}) [${c[2]}]`);
  check('8.3', 'AVANCE normalizado a escala 0-100 sin confundir 1 con "1"', '0 fallos',
    fallos.length ? fallos.join(' | ') : '0 fallos', fallos.length === 0,
    'Colapsar ambos casos archivaria como terminadas las tareas al 1%');
});

run('8.4', 'Sin credenciales configuradas no se envía nada', () => {
  const env = envSupabase({}, { sinConfigurar: true });
  const res = env.api.SupabaseSync.mirrorBatch('JAIME OLIVO', [{ FOLIO: 'JO-1', CONCEPTO: 'X' }]);
  const silencioso = env.peticiones.length === 0 && res.skipped === true;
  check('8.4', 'El espejo queda inerte mientras no se configure', 'cero peticiones',
    `${env.peticiones.length} peticiones, skipped=${res.skipped}`, silencioso);
});

run('8.5', 'Un tracker se replica en `tasks` con upsert por dedupe_key', () => {
  const env = envSupabase({});
  env.api.SupabaseSync.mirrorBatch('JAIME OLIVO', [
    { FOLIO: 'JO-0009', CONCEPTO: 'REVISAR PLANOS', AVANCE: 1, ESTATUS: 'HECHO', RESPONSABLE: 'JAIME OLIVO' }
  ]);
  const envios = peticionesA(env, 'tasks');
  const url = envios.length ? envios[0].url : '';
  const cuerpo = envios.length ? JSON.parse(envios[0].params.payload)[0] : {};
  const ok = envios.length === 1 &&
             url.indexOf('on_conflict=dedupe_key') >= 0 &&
             String(envios[0].params.headers.Prefer).indexOf('merge-duplicates') >= 0 &&
             cuerpo.dedupe_key === 'JAIME OLIVO::JO-0009' &&
             cuerpo.avance === 100 &&
             cuerpo.source_sheet === 'JAIME OLIVO';
  check('8.5', 'Upsert a tasks con la clave y el AVANCE correctos', 'on_conflict=dedupe_key, avance=100',
    `envios=${envios.length}, key=${cuerpo.dedupe_key}, avance=${cuerpo.avance}`, ok);
});

run('8.6', 'Una hoja de ventas se replica en `quotes`, no en `tasks`', () => {
  const env = envSupabase({});
  env.api.SupabaseSync.mirrorBatch('ANTONIA_VENTAS', [
    { FOLIO: 'AV-0042', CLIENTE: 'ACME', CONCEPTO: 'NAVE', VENDEDOR: 'ANTONIA PINEDA LOPEZ', MONTO: '$1,500.50' }
  ]);
  const aQuotes = peticionesA(env, 'quotes');
  const aTasks = peticionesA(env, 'tasks');
  const cuerpo = aQuotes.length ? JSON.parse(aQuotes[0].params.payload)[0] : {};
  const ok = aQuotes.length === 1 && aTasks.length === 0 &&
             aQuotes[0].url.indexOf('on_conflict=folio') >= 0 &&
             cuerpo.folio === 'AV-0042' && cuerpo.monto === 1500.5;
  check('8.6', 'Ruteo por tipo de hoja y monto limpiado', 'quotes, folio, monto=1500.5',
    `quotes=${aQuotes.length}, tasks=${aTasks.length}, monto=${cuerpo.monto}`, ok);
});

run('8.7', 'INVOLUCRADOS compuesto no ensucia `people` (AGENTS.md §3)', () => {
  const env = envSupabase({}, {
    people: [
      { id: 'uuid-ramiro', nombre: 'RAMIRO RODRIGUEZ' },
      { id: 'uuid-alfonso', nombre: 'ALFONSO CORREA' }
    ]
  });
  env.api.SupabaseSync.mirrorBatch('RAMIRO RODRIGUEZ', [
    { FOLIO: 'RR-1', CONCEPTO: 'X', INVOLUCRADOS: 'RAMIRO RODRIGUEZ, ALFONSO CORREA, TERESA GARZA' }
  ]);
  const cuerpo = JSON.parse(peticionesA(env, 'tasks')[0].params.payload)[0];
  const ok = cuerpo.assignee_id === 'uuid-ramiro' &&
             cuerpo.assignee_raw === 'RAMIRO RODRIGUEZ, ALFONSO CORREA, TERESA GARZA';
  check('8.7', 'Se resuelve la primera persona y se conserva el texto completo', 'uuid-ramiro',
    `assignee_id=${cuerpo.assignee_id}`, ok,
    'Nunca guardar el string compuesto como si fuera una persona');
});

run('8.8', 'Si Supabase falla, el guardado en Sheets NO se rompe', () => {
  const env = envSupabase({ 'JAIME OLIVO': tracker([]), 'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']] },
                          { lanzar: true });
  const res = env.api.apiSaveTrackerBatch('JAIME OLIVO', [{ CONCEPTO: 'TAREA CRITICA', FECHA: '08/07/26', _tempId: 't9' }], 'JAIME_OLIVO');
  const enLaHoja = countRowsContaining(env, 'JAIME OLIVO', 'TAREA CRITICA');
  const ok = res && res.success === true && enLaHoja === 1;
  check('8.8', 'Con la red caída la tarea se guarda igual', 'success=true y 1 fila en la hoja',
    `success=${res && res.success}, filas=${enLaHoja}`, ok,
    'INVARIANTE: mejor perder una réplica que una tarea');
});

run('8.9', 'registrarLog se replica en `system_log`', () => {
  const env = envSupabase({ 'LOG_SISTEMA': [['FECHA', 'USUARIO', 'ACCION', 'DETALLES']] });
  env.api.registrarLog('LUIS_CARLOS', 'LOGIN', 'Acceso exitoso');
  const envios = peticionesA(env, 'system_log');
  const cuerpo = envios.length ? JSON.parse(envios[0].params.payload)[0] : {};
  const ok = envios.length === 1 && cuerpo.usuario === 'LUIS_CARLOS' && cuerpo.accion === 'LOGIN' &&
             /^\d{4}-\d{2}-\d{2}T/.test(String(cuerpo.fecha_hora));
  check('8.9', 'Auditoría espejada con fecha ISO', '1 envío con usuario y accion',
    `envios=${envios.length}, usuario=${cuerpo.usuario}, fecha=${cuerpo.fecha_hora}`, ok);
});

run('8.11', 'normalizeStatus colapsa las 45 variantes reales', () => {
  const S = envSupabase({}).api.SupabaseSync;
  const casos = [
    // Las 19 formas de escribir ASIGNADO que había en la base.
    ['ASIGNADO', 'ASIGNADO'], ['Asignado', 'ASIGNADO'], ['asignado', 'ASIGNADO'],
    ['ASIGNADA', 'ASIGNADO'], ['asignada', 'ASIGNADO'], ['ASIGANDO', 'ASIGNADO'],
    ['ASIGANDA', 'ASIGNADO'], ['ASIGADO', 'ASIGNADO'], ['ASIGANDOA', 'ASIGNADO'],
    ['ASIGANADO', 'ASIGNADO'], ['ASIGANADA', 'ASIGNADO'], ['ASIGANDa', 'ASIGNADO'],
    ['asigando', 'ASIGNADO'], ['asigado', 'ASIGNADO'], ['asiganda', 'ASIGNADO'],
    ['asigndo', 'ASIGNADO'], ['aSIGNADO', 'ASIGNADO'], ['asignadO', 'ASIGNADO'],
    ['asignADO', 'ASIGNADO'],
    ['PEDIENTE', 'PENDIENTE'], ['Pendiente', 'PENDIENTE'],
    ['Falta Información', 'FALTA INFORMACION'],
    ['En Revisión', 'EN REVISION'],
    ['Cancelada x Planta', 'CANCELADA'],
    ['Perdida x Tiempo', 'PERDIDA POR TIEMPO'],
    ['perdida por tiempo', 'PERDIDA POR TIEMPO'],
    ['BIERTO', 'ABIERTO'], ['abierto', 'ABIERTO'],
    ['en proceso', 'EN PROCESO'],
    ['Pendiente Visita', 'PENDIENTE VISITA'],
    // Marcadores de vacío.
    ['-', ''], ['-\n-', ''], ['', ''], [null, ''], ['   ', '']
  ];
  const fallos = casos.filter(c => S.normalizeStatus(c[0]) !== c[1])
                      .map(c => `${JSON.stringify(c[0])} -> ${JSON.stringify(S.normalizeStatus(c[0]))} (esperado ${c[1]})`);
  check('8.11', 'Estatus canónico en la escritura', '0 fallos',
    fallos.length ? fallos.slice(0, 4).join(' | ') : '0 fallos', fallos.length === 0,
    'Sin esto la columna vuelve a acumular variantes en cada captura');
});

run('8.12', 'Un estatus desconocido se conserva, no se descarta', () => {
  const S = envSupabase({}).api.SupabaseSync;
  const nuevo = S.normalizeStatus('EN LICITACION');
  const basura = S.normalizeStatus('RAM');
  const ok = nuevo === 'EN LICITACION' && basura === 'RAM';
  check('8.12', 'Un valor no reconocido pasa tal cual', 'se conserva',
    `'EN LICITACION'->${JSON.stringify(nuevo)}, 'RAM'->${JSON.stringify(basura)}`, ok,
    'Si el equipo empieza a usar un estatus nuevo, tirarlo perderia el dato');
});

run('8.13', 'Normalizar no altera el auto-archivado', () => {
  const env = envSupabase({});
  const S = env.api.SupabaseSync;
  const isTerminal = env.api.isTerminalStatus;
  const valores = ['ASIGNADO', 'Asignado', 'ASIGNADA', 'PEDIENTE', 'Perdida x Tiempo',
                   'perdida por tiempo', 'Cancelada x Planta', 'SUSPENDIDA',
                   'HECHO', 'TERMINADO', 'GANADA', 'PERDIDA', '-', ''];
  const fallos = valores.filter(v => isTerminal(v) !== isTerminal(S.normalizeStatus(v)))
                        .map(v => `${JSON.stringify(v)}: ${isTerminal(v)} -> ${isTerminal(S.normalizeStatus(v))}`);
  check('8.13', 'El estado terminal se conserva tras normalizar', '0 cambios',
    fallos.length ? fallos.join(' | ') : '0 cambios', fallos.length === 0,
    'Un alias mal mapeado archivaria o desarchivaria tareas');
});

run('8.14', 'El estatus se normaliza al escribir en la base', () => {
  const env = envSupabase({});
  env.api.SupabaseSync.mirrorBatch('JAIME OLIVO', [
    { FOLIO: 'JO-1', CONCEPTO: 'X', ESTATUS: 'ASIGANDA' }
  ]);
  const cuerpo = JSON.parse(peticionesA(env, 'tasks')[0].params.payload)[0];
  check('8.14', 'La errata ASIGANDA llega como ASIGNADO', 'ASIGNADO',
    JSON.stringify(cuerpo.status), cuerpo.status === 'ASIGNADO');
});

run('8.15', 'tasks.status nunca se envía nulo (la columna es NOT NULL)', () => {
  const env = envSupabase({});
  env.api.SupabaseSync.mirrorBatch('JAIME OLIVO', [{ FOLIO: 'JO-2', CONCEPTO: 'SIN ESTATUS' }]);
  const cuerpo = JSON.parse(peticionesA(env, 'tasks')[0].params.payload)[0];
  const ok = cuerpo.status === '';
  check('8.15', 'Sin estatus se envía cadena vacía, no null', '""',
    JSON.stringify(cuerpo.status), ok,
    'tasks.status tiene NOT NULL: un null aborta el upsert entero');
});

run('8.10', 'Las credenciales no están en el fuente', () => {
  const hardcodeada = /SUPABASE_(URL|KEY)\s*[:=]\s*["']http|sb_secret_|eyJhbGciOi/.test(CODIGO_SRC);
  check('8.10', 'SUPABASE_URL/KEY solo por Propiedades del Script', 'sin credenciales en CODIGO.js',
    hardcodeada ? 'HAY credenciales en el fuente' : 'sin credenciales', !hardcodeada);
});

// ======================================================================
// REPORTE
// ======================================================================
const total = results.length;
const pasadas = results.filter(r => r.ok).length;
const fallidas = total - pasadas;

const ANSI = { green: '\x1b[32m', red: '\x1b[31m', bold: '\x1b[1m', dim: '\x1b[2m', reset: '\x1b[0m' };

let lastSec = '';
console.log(`\n${ANSI.bold}RESULTADOS DE PRUEBAS — CODIGO.js (mocks de Google Apps Script)${ANSI.reset}\n`);
results.forEach(r => {
  if (r.seccion !== lastSec) { console.log(`\n${ANSI.bold}${r.seccion}${ANSI.reset}`); lastSec = r.seccion; }
  const tag = r.ok ? `${ANSI.green}PASA${ANSI.reset}` : `${ANSI.red}FALLA${ANSI.reset}`;
  console.log(`  [${tag}] ${r.id} · ${r.nombre}`);
  if (!r.ok) {
    console.log(`         ${ANSI.dim}esperado:${ANSI.reset} ${r.esperado}`);
    console.log(`         ${ANSI.dim}obtenido:${ANSI.reset} ${r.obtenido}`);
    if (r.nota) console.log(`         ${ANSI.dim}nota:${ANSI.reset} ${r.nota}`);
  }
});

console.log(`\n${ANSI.bold}TOTAL:${ANSI.reset} ${total}   ${ANSI.green}PASAN: ${pasadas}${ANSI.reset}   ${ANSI.red}FALLAN: ${fallidas}${ANSI.reset}\n`);

// Reporte Markdown
const lines = [];
lines.push('# Resultados de pruebas — Migración Holtmont');
lines.push('');
lines.push('> Generado automáticamente por `node tests/gas/run_tests.js` contra `CODIGO.js` con mocks de Google Apps Script.');
lines.push('');
lines.push(`**Total:** ${total} · **Pasan:** ${pasadas} · **Fallan:** ${fallidas}`);
lines.push('');
let sec = '';
results.forEach(r => {
  if (r.seccion !== sec) {
    sec = r.seccion;
    lines.push('');
    lines.push(`## ${sec}`);
    lines.push('');
    lines.push('| # | Prueba | Esperado | Obtenido | Resultado |');
    lines.push('|---|--------|----------|----------|-----------|');
  }
  // Se enmascaran los valores volátiles (timestamps) para que volver a correr
  // la suite no genere diffs espurios en el reporte versionado.
  const esc = (s) => String(s)
    .replace(/"timestamp":\s*\d+/g, '"timestamp":<ts>')
    .replace(/"dateStr":\s*"[^"]*"/g, '"dateStr":"<fecha>"')
    .replace(/\|/g, '\\|');
  lines.push(`| ${r.id} | ${esc(r.nombre)} | ${esc(r.esperado)} | ${esc(r.obtenido)} | ${r.ok ? '✅ PASA' : '❌ FALLA'} |`);
  if (r.nota) lines.push(`| | _${esc(r.nota)}_ | | | |`);
});
lines.push('');
fs.writeFileSync(path.resolve(__dirname, 'RESULTADOS.md'), lines.join('\n'));
console.log(`Reporte escrito en tests/gas/RESULTADOS.md`);

process.exit(fallidas > 0 ? 1 : 0);
