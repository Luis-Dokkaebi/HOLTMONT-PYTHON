/**
 * ======================================================================
 * EVALUADOR MÍNIMO DE FÓRMULAS DE FORMATO CONDICIONAL (SEMÁFORO)
 * ======================================================================
 * applyTrafficLightToSheet() no pinta celdas: registra reglas
 * `whenFormulaSatisfied()`. Para verificar el color real que vería el
 * usuario, evaluamos la fórmula generada sustituyendo:
 *   - UPPER(TRIM($<col><fila>))="X"  -> comparación contra la clasificación
 *   - ISNUMBER($<col><fila>)         -> TRUE (la celda tiene fecha válida)
 *   - ROW()>N                        -> TRUE (fila de datos)
 *   - (TODAY() - INT($<col><fila>))  -> antigüedad en días
 * y resolviendo los AND() anidados.
 */

function splitTopLevel(expr) {
  const parts = [];
  let depth = 0, current = '', inStr = false;
  for (const ch of expr) {
    if (ch === '"') inStr = !inStr;
    if (!inStr) {
      if (ch === '(') depth++;
      else if (ch === ')') depth--;
      else if (ch === ',' && depth === 0) { parts.push(current); current = ''; continue; }
    }
    current += ch;
  }
  if (current.trim() !== '') parts.push(current);
  return parts.map(p => p.trim());
}

function andToJs(expr) {
  expr = expr.trim();
  const m = /^AND\s*\(([\s\S]*)\)$/.exec(expr);
  if (m) {
    return '(' + splitTopLevel(m[1]).map(andToJs).join(' && ') + ')';
  }
  return '(' + expr + ')';
}

/**
 * Evalúa una fórmula de semáforo.
 * @param {string} formula   fórmula tal cual la generó CODIGO.js (inicia con '=')
 * @param {{clase: string, dias: number}} ctx
 * @returns {boolean}
 */
function evalTrafficFormula(formula, ctx) {
  let f = String(formula).replace(/^=/, '');

  // (TODAY() - INT($D2))  ->  días de antigüedad
  f = f.replace(/\(\s*TODAY\(\)\s*-\s*INT\(\$[A-Z]+\d+\)\s*\)/g, `(${ctx.dias})`);
  // UPPER(TRIM($J2))="A"  ->  TRUE/FALSE
  f = f.replace(/UPPER\(TRIM\(\$[A-Z]+\d+\)\)\s*=\s*"([^"]*)"/g,
    (_, lit) => (String(ctx.clase).toUpperCase().trim() === lit ? 'true' : 'false'));
  // ISNUMBER($D2) -> la celda de fecha es numérica (fecha válida)
  f = f.replace(/ISNUMBER\(\$[A-Z]+\d+\)/g, ctx.fechaValida === false ? 'false' : 'true');
  // ROW()>2 -> fila de datos
  f = f.replace(/ROW\(\)\s*>\s*\d+/g, 'true');

  const js = andToJs(f);
  if (/[A-Z]{2,}\s*\(/.test(js)) {
    throw new Error('Fórmula con función no soportada por el evaluador: ' + formula);
  }
  // eslint-disable-next-line no-new-func
  return !!Function(`"use strict"; return (${js});`)();
}

/**
 * Determina el color de fondo que Google Sheets aplicaría: gana la
 * PRIMERA regla cuya fórmula se cumple (orden de la lista de reglas).
 * @returns {string|null} color hex o null si ninguna regla aplica
 */
function resolveColor(rules, ctx) {
  for (const rule of rules) {
    const cond = rule.getBooleanCondition && rule.getBooleanCondition();
    if (!cond || cond.getCriteriaType() !== 'CUSTOM_FORMULA') continue;
    const formula = cond.getCriteriaValues()[0];
    if (!/TODAY\(\)/.test(formula)) continue;
    if (evalTrafficFormula(formula, ctx)) return rule.getBackground();
  }
  return null;
}

const COLOR_NAME = {
  '#00FF00': 'VERDE',
  '#FFFF00': 'AMARILLO',
  '#FF0000': 'ROJO',
  null: 'SIN COLOR'
};

module.exports = { evalTrafficFormula, resolveColor, COLOR_NAME };
