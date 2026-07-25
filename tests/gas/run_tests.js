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
  // El plan dice "AA = límite 14 días" -> a los 15 días debería estar VENCIDO (rojo)
  const color15 = resolveColor(rules, { clase: 'AA', dias: 15 });
  check('1.4', 'AA a los 15 días (límite del plan = 14)', COLOR_NAME['#FF0000'],
    COLOR_NAME[color15] || String(color15), color15 === '#FF0000',
    'CODIGO.js usa límite 15 (addRulePair("AA", 15, 3)), el plan documenta 14');
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
  check('5.1c', 'MAP COT de la etapa CD pasa de ⚪ a 🔴', '🔴 CD', mapcot || '(vacío)', /🔴/.test(mapcot));

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
  check('5.2d', 'MAP COT de CD cambia a 🟢', '🟢 CD', mapcot || '(vacío)', /🟢/.test(mapcot));
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
    return /console\.warn\([^)]*not implemented|stub/i.test(body) || !/fetch\(/.test(body);
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
  const esc = (s) => String(s).replace(/\|/g, '\\|');
  lines.push(`| ${r.id} | ${esc(r.nombre)} | ${esc(r.esperado)} | ${esc(r.obtenido)} | ${r.ok ? '✅ PASA' : '❌ FALLA'} |`);
  if (r.nota) lines.push(`| | _${esc(r.nota)}_ | | | |`);
});
lines.push('');
fs.writeFileSync(path.resolve(__dirname, 'RESULTADOS.md'), lines.join('\n'));
console.log(`Reporte escrito en tests/gas/RESULTADOS.md`);

process.exit(fallidas > 0 ? 1 : 0);
