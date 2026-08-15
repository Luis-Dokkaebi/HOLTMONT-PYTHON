/**
 * ======================================================================
 * HOLTMONT WORKSPACE V158 - SCRIPTMASTER EDITION
 * Backend: Lógica optimizada con detección de Especialidad para Filtros
 * Actualización: Soporte para Múltiples PPC (Interno, Preoperativo, Cliente)
 * ======================================================================
 */

var DEMO_MODE = false; // HOTFIX: MODO DEMO
const SS = SpreadsheetApp.getActiveSpreadsheet();

// --- CONFIGURACIÓN ---
const APP_CONFIG = {
  folderIdUploads: "", 
  ppcSheetName: "PPCV3",          
  draftSheetName: "PPC_BORRADOR", 
  salesSheetName: "Datos",        
  logSheetName: "LOG_SISTEMA",
  directorySheetName: "DB_DIRECTORY", // NUEVO: Hoja de Directorio
  // NUEVAS HOJAS PARA DETALLES DE WORK ORDER
  woMaterialsSheet: "DB_WO_MATERIALES",
  woLaborSheet: "DB_WO_MANO_OBRA",
  woToolsSheet: "DB_WO_HERRAMIENTAS",
  woEquipSheet: "DB_WO_EQUIPOS",
  woProgramSheet: "DB_WO_PROGRAMA"
};

const FOLIO_CONFIG = {
  SHEET_NAME: 'ANTONIA_VENTAS',
  COLUMN_NAME: 'Folio'
};

const INITIAL_DIRECTORY = [
    { name: "ANTONIA_VENTAS", dept: "VENTAS", type: "VENTAS" },
    { name: "JUDITH ECHAVARRIA", dept: "VENTAS", type: "ESTANDAR" },
    { name: "EDUARDO MANZANARES", dept: "VENTAS", type: "ESTANDAR" },
    { name: "RAMIRO RODRIGUEZ", dept: "VENTAS", type: "HIBRIDO" },
    { name: "SEBASTIAN PADILLA", dept: "VENTAS", type: "ESTANDAR" },
    { name: "CESAR GOMEZ", dept: "VENTAS", type: "ESTANDAR" },
    { name: "ALFONSO CORREA", dept: "VENTAS", type: "ESTANDAR" },
    { name: "TERESA GARZA", dept: "VENTAS", type: "HIBRIDO" },
    { name: "GUILLERMO DAMICO", dept: "VENTAS", type: "ESTANDAR" },
    { name: "ANGEL SALINAS", dept: "VENTAS", type: "HIBRIDO" },
    { name: "JUAN JOSE SANCHEZ", dept: "VENTAS", type: "ESTANDAR" },
    { name: "LUIS CARLOS", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "ANTONIO SALAZAR", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "ROCIO CASTRO", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "DANIA GONZALEZ", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "JUANY RODRIGUEZ", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "LAURA HUERTA", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "LILIANA MARTINEZ", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "DANIELA CASTRO", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "EDUARDO BENITEZ", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "ANTONIO CABRERA", dept: "ADMINISTRACION", type: "ESTANDAR" },
    { name: "ADMINISTRADOR", dept: "ADMINISTRACION", type: "HIBRIDO" },
    { name: "EDUARDO MANZANARES", dept: "HVAC", type: "ESTANDAR" },
    { name: "JUAN JOSE SANCHEZ", dept: "HVAC", type: "ESTANDAR" },
    { name: "SELENE BALDONADO", dept: "HVAC", type: "ESTANDAR" },
    { name: "ROLANDO MORENO", dept: "HVAC", type: "ESTANDAR" },
    { name: "MIGUEL GALLARDO", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    { name: "SEBASTIAN PADILLA", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    { name: "JEHU MARTINEZ", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    { name: "MIGUEL GONZALEZ", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    { name: "ALICIA RIVERA", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    { name: "RICARDO MENDO", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "CARLOS MENDEZ", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "REYNALDO GARCIA", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "INGE OLIVO", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "EDUARDO TERAN", dept: "CONSTRUCCION", type: "HIBRIDO" },
    { name: "EDGAR HOLT", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "ALEXIS TORRES", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "TERESA GARZA", dept: "CONSTRUCCION", type: "HIBRIDO" },
    { name: "RAMIRO RODRIGUEZ", dept: "CONSTRUCCION", type: "HIBRIDO" },
    { name: "GUILLERMO DAMICO", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "RUBEN PESQUEDA", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "JUDITH ECHAVARRIA", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "GISELA DOMINGUEZ", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "VANESSA DE LARA", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "NELSON MALDONADO", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "VICTOR ALMACEN", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "DIMAS RAMOS", dept: "EHS", type: "ESTANDAR" },
    { name: "CITLALI GOMEZ", dept: "EHS", type: "ESTANDAR" },
    { name: "AIMEE RAMIREZ", dept: "EHS", type: "ESTANDAR" },
    { name: "EDGAR HOLT", dept: "MAQUINARIA", type: "ESTANDAR" },
    { name: "ALEXIS TORRES", dept: "MAQUINARIA", type: "ESTANDAR" },
    { name: "ANGEL SALINAS", dept: "DISEÑO", type: "HIBRIDO" },
    { name: "EDGAR HOLT", dept: "DISEÑO", type: "ESTANDAR" },
    { name: "EDGAR LOPEZ", dept: "DISEÑO", type: "HIBRIDO" }
];

const DEFAULT_TRACKER_HEADERS = ['ID', 'ESPECIALIDAD', 'CONCEPTO', 'FECHA', 'RELOJ', 'AVANCE', 'ESTATUS', 'COMENTARIOS', 'ARCHIVO', 'CLASIFICACION', 'PRIORIDAD', 'FECHA_RESPUESTA'];
const DEFAULT_SALES_HEADERS = ['FOLIO', 'CLIENTE', 'CONCEPTO', 'VENDEDOR', 'FECHA', 'ESTATUS', 'COMENTARIOS', 'ARCHIVO', 'MONTO', 'F2', 'COTIZACION', 'TIMELINE', 'LAYOUT', 'AVANCE'];

// --- ESTRUCTURA ESTÁNDAR DE PROYECTOS (MODIFICADO) ---
// Aquí definimos los sub-proyectos automáticos.
// Se eliminó "PPC PROYECTO" y se agregaron los 3 específicos.
// Se conservan DOCUMENTOS, PLANOS, FOTOGRAFIAS, etc.
const STANDARD_PROJECT_STRUCTURE = [
  "NAVE",
  "AMPLIACION",
  "PPC INTERNO",      // NUEVO
  "PPC PREOPERATIVO", // NUEVO
  "PPC CLIENTE",      // NUEVO
  "DOCUMENTOS",       // PRESERVADO
  "PLANOS Y DISEÑOS", // PRESERVADO
  "FOTOGRAFIAS",      // PRESERVADO
  "CORRESPONDENCIA",  // PRESERVADO
  "REPORTES"          // PRESERVADO
];

// USUARIOS
// NOTA: el campo `email` es obligatorio para las notificaciones Make.com -> Outlook
// (ver AGENTS.md §5 "Emails Reales"). Si un usuario no tiene correo, NotifierService
// intenta derivarlo con resolveUserEmail() a partir del directorio.
const USER_DB = {
  "LUIS_CARLOS":      { pass: "admin2025", role: "ADMIN", label: "Administrador", email: "luis.carlos@holtmont.com" },
  "JESUS_CANTU":      { pass: "ppc2025",   role: "PPC_ADMIN", label: "PPC Manager", email: "jesus.cantu@holtmont.com" },
  "ANTONIA_VENTAS":   { pass: "tonita2025", role: "TONITA", label: "Ventas", email: "antonia.pineda@holtmont.com" },
  "JAIME_OLIVO":      { pass: "admin2025", role: "ADMIN_CONTROL", label: "Jaime Olivo", email: "jaime.olivo@holtmont.com" },
  "ANGEL_SALINAS":    { pass: "angel2025", role: "ANGEL_USER", label: "Angel Salinas", email: "angel.salinas@holtmont.com" },
  "TERESA_GARZA":     { pass: "tere2025",  role: "TERESA_USER", label: "Teresa Garza", email: "teresa.garza@holtmont.com" },
  "EDUARDO_TERAN":    { pass: "lalo2025",  role: "EDUARDO_USER", label: "Eduardo Teran", email: "eduardo.teran@holtmont.com" },
  "EDUARDO_MANZANARES":{ pass: "manzanares2025", role: "MANZANARES_USER", label: "Eduardo Manzanares", email: "eduardo.manzanares@holtmont.com" },
  "RAMIRO_RODRIGUEZ": { pass: "ramiro2025", role: "RAMIRO_USER", label: "Ramiro Rodriguez", email: "ramiro.rodriguez@holtmont.com" },
  "SEBASTIAN_PADILLA":{ pass: "sebastian2025", role: "SEBASTIAN_USER", label: "Sebastian Padilla", email: "sebastian.padilla@holtmont.com" },
  "EDGAR_LOPEZ":      { pass: "edgar2025", role: "EDGAR_USER", label: "Edgar Lopez", email: "edgar.lopez@holtmont.com" },
  "PREWORK_ORDER":    { pass: "workorder2026", role: "WORKORDER_USER", label: "Workorder", email: "workorder@holtmont.com" }
};

// --- RUTEO ESPECIAL DE VENTAS ("LA LEY DE ANTONIA", AGENTS.md §3) ---
const SALES_ROUTING_CONFIG = {
  masterSalesSheet: "ANTONIA_VENTAS",     // Core de ventas (solo Toñita escribe aquí)
  antoniaPersonalSheet: "ANTONIA PINEDA LOPEZ", // Tracker personal de Toñita
  salesSuffixRegex: /\s*\(VENTAS\)/ig     // Sufijo que se purga a usuarios ajenos
};

// --- PREFIJOS DE FOLIO POR USUARIO/HOJA ---
const FOLIO_PREFIX_MAP = {
  "JAIME OLIVO": "JO",
  "JESUS CANTU": "JC",
  "LUIS CARLOS": "LC",
  "ADMINISTRADOR": "LC",
  "ANTONIA VENTAS": "AV",
  "ANTONIA PINEDA LOPEZ": "AP",
  "RAMIRO RODRIGUEZ": "RR",
  "SEBASTIAN PADILLA": "SP",
  "TERESA GARZA": "TG"
};
const FOLIO_PREFIX_FALLBACK = "PPC-";
const FOLIO_STOPWORDS = ["DE", "DEL", "LA", "LAS", "LOS", "Y", "EL"];

// --- PAPA CALIENTE / TIMELINE DE COTIZACIÓN (espejo de index.html) ---
const PROCESS_STEPS = ["L", "CD", "EP", "CI", "EV", "CEC", "RCC"];
const FULL_PROCESS_NAMES = {
  "L": "Levantamiento",
  "CD": "Calculo y Diseño",
  "EP": "Elaboracion Presupuesto",
  "CI": "Cotizacion Interna",
  "EV": "Estrategia Ventas",
  "CEC": "Cotizacion Enviada al cliente",
  "RCC": "Revision de Cotizacion Cliente"
};

// --- ESTATUS TERMINALES (auto-archivado y métricas) ---
const TERMINAL_STATUSES = ["HECHO", "DONE", "REALIZADO", "COMPLETADO", "TERMINADO", "CERRADO", "FINALIZADO"];
const WIN_STATUSES = ["GANADA", "GANADO", "APROBADA", "APROBADO", "VENDIDA", "VENDIDO", "CERRADA GANADA"];
const LOSS_STATUSES = ["PERDIDA", "PERDIDO", "CANCELADA", "CANCELADO", "DECLINADA", "RECHAZADA"];

// --- INTEGRACIÓN MAKE.COM -> OUTLOOK (AGENTS.md §5) ---
const NOTIFIER_CONFIG = {
  urlProperty: "MAKE_WEBHOOK_URL",   // Configurable en Propiedades del Script
  defaultUrl: "https://hook.us2.make.com/holtmont-tracker-notificaciones",
  enabledProperty: "MAKE_WEBHOOK_ENABLED",
  domain: "holtmont.com"
};

// --- AGENTE DE MÉTRICAS DE COTIZACIONES ---
const METRICS_CONFIG = {
  geminiKeyProperty: "GEMINI_API_KEY",
  lastReportProperty: "LAST_QUOTE_AGENT_REPORT",
  kpiSheetName: "KPI_COTIZACIONES",
  geminiModel: "gemini-1.5-flash",
  slaLimits: { "A": 3, "AA": 14, "AAA": 30 }
};

/* SERVICIO HTML */
function doGet(e) {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Holtmont Workspace')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/* HELPERS */
function findSheetSmart(name) {
  if (!name) return null;
  let sheet = SS.getSheetByName(name);
  if (sheet) return sheet;
  const clean = String(name).trim().toUpperCase();
  const all = SS.getSheets();
  for (let s of all) { if (s.getName().trim().toUpperCase() === clean) return s; }
  return null;
}

// DETECTOR DE CABECERAS INTELIGENTE
function findHeaderRow(values) {
  for (let i = 0; i < Math.min(100, values.length); i++) {
    const rowStr = values[i].map(c => String(c).toUpperCase().replace(/\n/g, " ").replace(/\s+/g, " ").trim()).join("|");
    if (rowStr.includes("ID_SITIO") || rowStr.includes("ID_PROYECTO")) return i;
    if (rowStr.includes("FOLIO") && rowStr.includes("CONCEPTO") && 
       (rowStr.includes("ALTA") || rowStr.includes("AVANCE") || rowStr.includes("STATUS") || rowStr.includes("FECHA"))) {
      return i;
    }
    if (rowStr.includes("ID") && rowStr.includes("RESPONSABLE")) return i;
    if ((rowStr.includes("FOLIO") || rowStr.includes("ID")) && 
        (rowStr.includes("DESCRIPCI") || rowStr.includes("RESPONSABLE") || rowStr.includes("CONCEPTO"))) {
      return i;
    }
    if (rowStr.includes("CLIENTE") && (rowStr.includes("VENDEDOR") || rowStr.includes("AREA") || rowStr.includes("CLASIFICACION"))) return i;
    // SOPORTE PARA AGENDA PERSONAL Y HABITOS
    if (rowStr.includes("ID") && rowStr.includes("TITULO") && rowStr.includes("USUARIO")) return i;
    if (rowStr.includes("ID") && rowStr.includes("HABITO") && rowStr.includes("USUARIO")) return i;
  }
  return -1;
}

function registrarLog(user, action, details) {
  try {
    let sheet = SS.getSheetByName(APP_CONFIG.logSheetName);
    if (!sheet) {
      sheet = SS.insertSheet(APP_CONFIG.logSheetName);
      sheet.appendRow(["FECHA", "USUARIO", "ACCION", "DETALLES"]);
    }
    sheet.appendRow([new Date(), user, action, details]);
  } catch (e) { console.error(e); }

  // Espejo en Supabase.system_log. Aparte del try/catch anterior a propósito:
  // un fallo de red no debe impedir que el log quede en la hoja, ni al revés.
  try { SupabaseSync.mirrorLog(user, action, details); }
  catch (e) { console.warn("Espejo de log fallido: " + e.toString()); }
}

/* LOGIN */
function apiLogin(username, password) {
  const userKey = String(username).trim().toUpperCase();
  const user = USER_DB[userKey];
  if (user && user.pass === password) {
    registrarLog(userKey, "LOGIN", `Acceso exitoso (${user.role})`);
    return { success: true, role: user.role, name: user.label, username: userKey };
  }
  registrarLog(userKey || "ANONIMO", "LOGIN_FAIL", "Credenciales incorrectas");
  return { success: false, message: 'Usuario o contraseña incorrectos.' };
}

function apiLogout(username) {
  registrarLog(username || "DESCONOCIDO", "LOGOUT", "Sesión cerrada");
  return { success: true };
}

function getDirectoryFromDB() {
  const lock = LockService.getScriptLock();
  try {
      if (lock.tryLock(5000)) {
          let sheet = findSheetSmart(APP_CONFIG.directorySheetName);
          
          // CREAR SI NO EXISTE
          if (!sheet) {
              sheet = SS.insertSheet(APP_CONFIG.directorySheetName);
          }

          // MIGRACIÓN/POBLADO AUTOMÁTICO (Si está vacía o solo tiene encabezados)
          if (sheet.getLastRow() < 2) {
              sheet.clear(); // Limpiar por si acaso el usuario puso encabezados manuales incorrectos
              const headers = ["NOMBRE", "DEPARTAMENTO", "TIPO_HOJA"];
              sheet.appendRow(headers);
              
              // Populate from INITIAL_DIRECTORY
              const rows = INITIAL_DIRECTORY.map(u => [u.name, u.dept, u.type]);
              if (rows.length > 0) {
                  sheet.getRange(2, 1, rows.length, 3).setValues(rows);
              }
              SpreadsheetApp.flush();
              registrarLog("SISTEMA", "MIGRACION_DB", "Se pobló DB_DIRECTORY (estaba vacía).");
          }

          const data = sheet.getDataRange().getValues();
          if (data.length < 2) return [];

          // Parse Data
          const headers = data[0].map(h => String(h).toUpperCase().trim());
          const nameIdx = headers.indexOf("NOMBRE");
          const deptIdx = headers.indexOf("DEPARTAMENTO");
          const typeIdx = headers.indexOf("TIPO_HOJA");

          if (nameIdx === -1) return [];

          const directory = [];
          for (let i = 1; i < data.length; i++) {
              const row = data[i];
              if (row[nameIdx]) {
                  directory.push({
                      name: String(row[nameIdx]).trim(),
                      dept: (deptIdx > -1) ? String(row[deptIdx]).trim() : "GENERAL",
                      type: (typeIdx > -1) ? String(row[typeIdx]).trim() : "ESTANDAR"
                  });
              }
          }
          return directory;
      }
  } catch (e) {
      console.error(e);
      // Fallback in case of error
      return INITIAL_DIRECTORY;
  } finally {
      lock.releaseLock();
  }
  return INITIAL_DIRECTORY;
}

function apiAddEmployee(payload) {
    const lock = LockService.getScriptLock();
    try {
        if (lock.tryLock(10000)) {
            const { name, dept, type } = payload;
            const cleanName = String(name).toUpperCase().trim();
            if (!cleanName) return { success: false, message: "Nombre inválido" };

            let sheet = findSheetSmart(APP_CONFIG.directorySheetName);
            if (!sheet) {
                // Should have been created by getDirectoryFromDB, but ensure it exists
                getDirectoryFromDB();
                sheet = findSheetSmart(APP_CONFIG.directorySheetName);
            }

            // Check duplicate
            const data = sheet.getDataRange().getValues();
            for(let i=1; i<data.length; i++) {
                if (String(data[i][0]).toUpperCase().trim() === cleanName) {
                    return { success: false, message: "El usuario ya existe." };
                }
            }

            // Add to DB
            sheet.appendRow([cleanName, dept, type]);

            // Create Sheets based on Type
            const createSheetIfMissing = (sName, headers) => {
                let s = findSheetSmart(sName);
                if (!s) {
                    s = SS.insertSheet(sName);
                    s.appendRow(headers);
                    s.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#e6e6e6");
                    // Conditional Formatting (Basic)
                    try {
                        const rule = SpreadsheetApp.newConditionalFormatRule()
                            .whenTextEqualTo("100")
                            .setBackground("#d4edda")
                            .setRanges([s.getRange("F:F")]) // Assuming Avance is commonly around F
                            .build();
                        s.setConditionalFormatRules([rule]);
                    } catch(e){}
                }
            };

            if (type === 'ESTANDAR' || type === 'HIBRIDO') {
                createSheetIfMissing(cleanName, DEFAULT_TRACKER_HEADERS);
            }
            if (type === 'VENTAS' || type === 'HIBRIDO') {
                createSheetIfMissing(cleanName + " (VENTAS)", DEFAULT_SALES_HEADERS);
            }

            registrarLog("ADMIN", "ADD_EMPLOYEE", `Usuario: ${cleanName}, Tipo: ${type}`);
            return { success: true };
        }
    } catch(e) {
        return { success: false, message: e.toString() };
    } finally {
        lock.releaseLock();
    }
}

function apiDeleteEmployee(name) {
    const lock = LockService.getScriptLock();
    try {
        if (lock.tryLock(10000)) {
            const cleanName = String(name).toUpperCase().trim();
            const sheet = findSheetSmart(APP_CONFIG.directorySheetName);
            if (!sheet) return { success: false, message: "No existe DB_DIRECTORY" };

            const data = sheet.getDataRange().getValues();
            let rowIndex = -1;
            for(let i=1; i<data.length; i++) {
                if (String(data[i][0]).toUpperCase().trim() === cleanName) {
                    rowIndex = i + 1; // 1-based
                    break;
                }
            }

            if (rowIndex > -1) {
                sheet.deleteRow(rowIndex);
                registrarLog("ADMIN", "DELETE_EMPLOYEE", `Usuario eliminado: ${cleanName}`);
                return { success: true };
            }
            return { success: false, message: "Usuario no encontrado." };
        }
    } catch(e) {
        return { success: false, message: e.toString() };
    } finally {
        lock.releaseLock();
    }
}

function getSystemConfig(role) {
  const fullDirectory = getDirectoryFromDB();

  const allDepts = {
      "CONSTRUCCION": { label: "Construcción", icon: "fa-hard-hat", color: "#e83e8c" },
      "COMPRAS": { label: "Compras/Almacén", icon: "fa-shopping-cart", color: "#198754" },
      "EHS": { label: "Seguridad (EHS)", icon: "fa-shield-alt", color: "#dc3545" },
      "DISEÑO": { label: "Diseño & Ing.", icon: "fa-drafting-compass", color: "#0d6efd" },
      "ELECTROMECANICA": { label: "Electromecánica", icon: "fa-bolt", color: "#ffc107" },
      "HVAC": { label: "HVAC", icon: "fa-fan", color: "#fd7e14" },
      "ADMINISTRACION": { label: "Administración", icon: "fa-briefcase", color: "#6f42c1" },
      "VENTAS": { label: "Ventas", icon: "fa-handshake", color: "#0dcaf0" },
      "MAQUINARIA": { label: "Maquinaria", icon: "fa-truck", color: "#20c997" }
  };

  const ppcModuleMaster = { id: "PPC_MASTER", label: "PPC Maestro", icon: "fa-tasks", color: "#fd7e14", type: "ppc_native" };
  const ppcModuleWeekly = { id: "WEEKLY_PLAN", label: "Planeación Semanal", icon: "fa-calendar-alt", color: "#6f42c1", type: "weekly_plan_view" };
  // const ecgModule = { id: "ECG_SALES", label: "Monitor Vivos", icon: "fa-heartbeat", color: "#d63384", type: "ecg_dashboard" };
  const kpiModule = { id: "KPI_DASHBOARD", label: "KPI Performance", icon: "fa-chart-line", color: "#d63384", type: "kpi_dashboard_view" };

  if (role === 'TONITA') return { 
      departments: { "VENTAS": allDepts["VENTAS"] }, 
      allDepartments: allDepts, 
      staff: [ { name: "ANTONIA_VENTAS", dept: "VENTAS" } ], 
      directory: fullDirectory, 
      specialModules: [ ppcModuleMaster, ppcModuleWeekly ],
      accessProjects: false 
  };
  
  if (role === 'ANGEL_USER') {
    return {
      departments: {},
      allDepartments: allDepts, 
      staff: [ { name: "ANGEL SALINAS", dept: "DISEÑO" } ], 
      directory: fullDirectory, 
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#0d6efd", type: "mirror_staff", target: "ANGEL SALINAS" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "ANGEL SALINAS (VENTAS)" }
      ],
      accessProjects: false 
    };
  }

  if (role === 'TERESA_USER') {
    return {
      departments: {},
      allDepartments: allDepts, 
      staff: [ { name: "TERESA GARZA", dept: "CONSTRUCCION" } ], 
      directory: fullDirectory, 
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#e83e8c", type: "mirror_staff", target: "TERESA GARZA" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "TERESA GARZA (VENTAS)" }
      ],
      accessProjects: false 
    };
  }

  if (role === 'EDUARDO_USER') {
    return {
      departments: {},
      allDepartments: allDepts, 
      staff: [ { name: "EDUARDO TERAN", dept: "CONSTRUCCION" } ], 
      directory: fullDirectory, 
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#fd7e14", type: "mirror_staff", target: "EDUARDO TERAN" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "EDUARDO TERAN (VENTAS)" }
      ],
      accessProjects: false 
    };
  }

  if (role === 'MANZANARES_USER') {
    return {
      departments: {},
      allDepartments: allDepts,
      staff: [ { name: "EDUARDO MANZANARES", dept: "HVAC" } ],
      directory: fullDirectory,
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#fd7e14", type: "mirror_staff", target: "EDUARDO MANZANARES" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "EDUARDO MANZANARES (VENTAS)" }
      ],
      accessProjects: false
    };
  }

  if (role === 'RAMIRO_USER') {
    return {
      departments: {},
      allDepartments: allDepts, 
      staff: [ { name: "RAMIRO RODRIGUEZ", dept: "CONSTRUCCION" } ], 
      directory: fullDirectory, 
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#20c997", type: "mirror_staff", target: "RAMIRO RODRIGUEZ" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "RAMIRO RODRIGUEZ (VENTAS)" }
      ],
      accessProjects: false 
    };
  }

  if (role === 'SEBASTIAN_USER') {
    return {
      departments: {},
      allDepartments: allDepts,
      staff: [ { name: "SEBASTIAN PADILLA", dept: "ELECTROMECANICA" } ],
      directory: fullDirectory,
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#ffc107", type: "mirror_staff", target: "SEBASTIAN PADILLA" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "SEBASTIAN PADILLA (VENTAS)" }
      ],
      accessProjects: false
    };
  }

  if (role === 'EDGAR_USER') {
    return {
      departments: {},
      allDepartments: allDepts,
      staff: [ { name: "EDGAR LOPEZ", dept: "DISEÑO" } ],
      directory: fullDirectory,
      specialModules: [
          { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: "#0d6efd", type: "mirror_staff", target: "EDGAR LOPEZ" },
          { id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: "EDGAR LOPEZ (VENTAS)" }
      ],
      accessProjects: false
    };
  }

  if (role === 'WORKORDER_USER') {
    const woModule = { ...ppcModuleMaster, label: "Pre Work Order" };
    return {
      departments: {},
      allDepartments: allDepts,
      staff: [],
      directory: fullDirectory,
      specialModules: [ woModule ],
      accessProjects: false
    };
  }

  const ppcModules = [ ppcModuleMaster, ppcModuleWeekly ];
  
  if (role === 'PPC_ADMIN') return { 
      departments: {}, 
      allDepartments: allDepts, 
      staff: [], 
      directory: fullDirectory, 
      specialModules: ppcModules,
      accessProjects: true 
  };
  
  if (role === 'ADMIN_CONTROL') {
    return {
      departments: allDepts, allDepartments: allDepts, staff: fullDirectory, directory: fullDirectory,
      specialModules: [
        { id: "PPC_DINAMICO", label: "Tracker", icon: "fa-layer-group", color: "#e83e8c", type: "ppc_dynamic_view" },
        ...ppcModules,
        { id: "MIRROR_TONITA", label: "Monitor Toñita", icon: "fa-eye", color: "#0dcaf0", type: "mirror_staff", target: "ANTONIA_VENTAS" },
        { id: "ADMIN_TRACKER", label: "Control", icon: "fa-clipboard-list", color: "#6f42c1", type: "mirror_staff", target: "ADMINISTRADOR" }
      ],
      accessProjects: true 
    };
  }

  // Default ADMIN (LUIS_CARLOS falls here with role 'ADMIN')
  const defaultModules = [ ...ppcModules, { id: "MIRROR_TONITA", label: "Monitor Toñita", icon: "fa-eye", color: "#0dcaf0", type: "mirror_staff", target: "ANTONIA_VENTAS" } ];
  if (role === 'ADMIN') {
      defaultModules.push(kpiModule);
  }

  return {
    departments: allDepts, allDepartments: allDepts, staff: fullDirectory, directory: fullDirectory,
    specialModules: defaultModules,
    accessProjects: true 
  };
}

/* FUNCIÓN PRINCIPAL DE DASHBOARD (RE-INGENIERÍA NATIVA) */
function generarDashboard() {
  // 4. Control de Acceso (RBAC - Session)
  const currentUserEmail = Session.getActiveUser().getEmail();
  const authorizedUser = "LUIS_CARLOS"; // En un entorno real, mapear email a usuario
  // Nota: Session.getActiveUser() puede estar vacío en cuentas personales o dependiendo de permisos.
  // Mantenemos la lógica de API token existente para la WebApp, pero añadimos check de sesión si se ejecuta manualmente.

  return apiFetchTeamKPIData("LUIS_CARLOS"); // Delegamos a la lógica interna
}

/* KPI ANALYSIS ENGINE - NATIVE JS IMPLEMENTATION */
function apiFetchTeamKPIData(username) {
  // MOCK DATA INJECTION
  if (DEMO_MODE) {
      // Simulación para VENTAS
      var dataVentasMock = [
        ["Eduardo Manzanares", 25, 3.5],
        ["Sebastian Padilla", 25, 2.8],
        ["Ramiro Rodriguez", 28, 4.1]
      ];
      // Simulación para TRACKER
      var dataTrackerMock = [
        ["Judith Echavarria", 23, 1.5],
        ["Eduardo Teran", 32, 2.0],
        ["Angel Salinas", 26, 1.8]
      ];

      return {
          success: true,
          ventas: dataVentasMock.map(function(r) { return {name: r[0], volume: r[1], efficiency: r[2]}; }),
          tracker: dataTrackerMock.map(function(r) { return {name: r[0], volume: r[1], efficiency: r[2]}; }),
          productivity: {
             labels: ["16-Dic", "17-Dic", "18-Dic", "19-Dic"],
             values: [2, 3, 3, 4]
          }
      };
  }

  // 4. Control de Acceso (Validación de Identidad)
  const user = USER_DB[String(username).toUpperCase().trim()];
  if (!user || user.role !== 'ADMIN') {
      return { success: false, message: 'Acceso Denegado. Privilegios insuficientes.' };
  }

  // Helper para procesar cada grupo (Map/Reduce Manual)
  const processGroup = (members) => {
    return members.map(name => {
       // 1. Acceso a Datos (SpreadsheetApp)
       // internalFetchSheetData usa SpreadsheetApp.getSheetByName() internamente
       const res = internalFetchSheetData(name);

       if (!res.success) {
           return { name: name, volume: 0, efficiency: 0, error: "Hoja no encontrada" };
       }

       const rows = res.data || [];

       // 2. Procesamiento de Arrays (Filter)
       const completed = rows.filter(row => {
           const st = String(row['ESTATUS'] || row['STATUS'] || '').toUpperCase();
           return st.includes('DONE') || st.includes('COMPLETED') || st.includes('FINALIZADO') || st.includes('TERMINADO');
       });

       // 2. Procesamiento de Arrays (Reduce/Calc Manual)
       let totalDays = 0;
       let count = 0;

       completed.forEach(t => {
           let start = t['FECHA'] || t['ALTA'] || t['FECHA INICIO'];
           // PRIORIDAD: FECHA TERMINO (REAL) > FECHA FIN > FECHA RESPUESTA (ESTIMADA)
           let end = t['FECHA TERMINO'] || t['FECHA FIN'] || t['FECHA_FIN'] || t['FECHA ENTREGA'] || t['FECHA RESPUESTA'];

           if (start && end) {
               const pDate = (d) => {
                   if (d instanceof Date) return d;
                   if (String(d).includes('/')) {
                       const pts = String(d).split('/');
                       if(pts.length===3) return new Date(pts[2].length===2 ? '20'+pts[2] : pts[2], pts[1]-1, pts[0]);
                   }
                   return new Date(d);
               };

               const d1 = pDate(start);
               const d2 = pDate(end);

               if (!isNaN(d1) && !isNaN(d2)) {
                   // Cálculo manual de diferencia en días
                   const diffTime = Math.abs(d2 - d1);
                   const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                   totalDays += diffDays;
                   count++;
               }
           }
       });

       const avg = count > 0 ? (totalDays / count).toFixed(1) : 0;

       return {
           name: name,
           volume: completed.length,
           efficiency: avg
       };
    });
  };

  // DYNAMIC FETCHING
  const fullDirectory = getDirectoryFromDB();

  // Filter for VENTAS
  const groupVentas = fullDirectory
      .filter(u => u.dept === 'VENTAS' && u.name !== 'ANTONIA_VENTAS')
      .map(u => u.name);

  // Filter for TRACKER (Non-Ventas, Non-Admin/System)
  const groupTracker = fullDirectory
      .filter(u => u.dept !== 'VENTAS' &&
                   u.dept !== 'ADMINISTRACION' &&
                   u.name !== 'ADMINISTRADOR' &&
                   u.name !== 'PREWORK_ORDER')
      .map(u => u.name);

  return {
      success: true,
      ventas: processGroup(groupVentas),
      tracker: processGroup(groupTracker)
  };
}

/* 5. TEST DE VALIDACIÓN (LOGGER) */
function test_DataIntegrity() {
  Logger.log("=== INICIO TEST DE INTEGRIDAD ===");

  const testUser = "Eduardo Manzanares";
  Logger.log("Verificando hoja para: " + testUser);

  const sheet = findSheetSmart(testUser);
  if (!sheet) {
      Logger.log("❌ FAIL: Hoja no encontrada.");
      return;
  }
  Logger.log("✅ OK: Hoja encontrada.");

  const res = internalFetchSheetData(testUser);
  if (!res.success) {
      Logger.log("❌ FAIL: Error leyendo datos: " + res.message);
      return;
  }

  const totalTareas = res.data.length;
  Logger.log("Volumen de datos encontrados: " + totalTareas);

  if (totalTareas === 0) {
      Logger.log("⚠️ WARNING: La hoja está vacía o no tiene tareas activas.");
  } else {
      const sample = res.data[0];
      const start = sample['FECHA'] || sample['ALTA'];
      Logger.log("Muestra de Fecha Inicio: " + start);
      if (start) {
          Logger.log("✅ OK: Formato de fecha detectado.");
      } else {
          Logger.log("⚠️ WARNING: Posible falta de columna FECHA.");
      }
  }

  Logger.log("=== FIN TEST ===");
}

/* 5. MOTOR DE LECTURA OPTIMIZADO */
function internalFetchSheetData(sheetName) {
  try {
    const sheet = findSheetSmart(sheetName);
    if (!sheet) return { success: true, data: [], history: [], headers: [], message: `Falta hoja: ${sheetName}` };
    const values = sheet.getDataRange().getValues();
    if (values.length < 2) return { success: true, data: [], history: [], headers: [], message: "Vacía" };
    const headerRowIndex = findHeaderRow(values);
    if (headerRowIndex === -1) return { success: true, data: [], headers: [], message: "Sin formato válido" };
    const rawHeaders = values[headerRowIndex].map(h => String(h).trim());
    const validIndices = [];
    const cleanHeaders = [];
    rawHeaders.forEach((h, index) => {
      if(h !== "") { validIndices.push(index); cleanHeaders.push(h); }
    });
    const dataRows = values.slice(headerRowIndex + 1);
    const activeTasks = [];
    const historyTasks = [];
    let isReadingHistory = false;
    for (let i = 0; i < dataRows.length; i++) {
      const row = dataRows[i];
      if (row.join("|").toUpperCase().includes("TAREAS REALIZADAS")) { isReadingHistory = true; continue; }
      if (row.every(c => c === "") || String(row[validIndices[0]]).toUpperCase() === String(cleanHeaders[0]).toUpperCase()) continue;
      let rowObj = {};
      let hasData = false;
      let sortDate = null;
      validIndices.forEach((colIndex, k) => {
        const headerName = cleanHeaders[k];
        let val = row[colIndex];
        if (val instanceof Date) {
           if (val.getFullYear() < 1900) val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "HH:mm");
           else {
              if (!sortDate) sortDate = val; 
              val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
           }
        } else if (typeof val === 'string') {
           if(val.match(/\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/)) {
               val = val.replace(/\b(\d{1,2})\/(\d{1,2})\/(\d{2,4})\b/g, (m, d, mm, y) => {
                   const yy = (y.length === 4) ? y.slice(-2) : y;
                   return `${d.padStart(2,'0')}/${mm.padStart(2,'0')}/${yy}`;
               });
           }
           else if (val.match(/^\d{4}-\d{2}-\d{2}$/)) {
               // Manual split to avoid TZ shifts
               const p = val.split('-');
               val = `${p[2]}/${p[1]}/${p[0].slice(-2)}`;
           }
        }
        if (val !== "" && val !== undefined) hasData = true;
        rowObj[headerName] = val;
      });
      if (hasData) {
        rowObj['_sortDate'] = sortDate;
        rowObj['_rowIndex'] = headerRowIndex + i + 2;
        if (isReadingHistory) historyTasks.push(rowObj); else activeTasks.push(rowObj);
      }
    }
    
    const dateSorter = (a, b) => {
      const dA = a['_sortDate'] instanceof Date ? a['_sortDate'].getTime() : 0;
      const dB = b['_sortDate'] instanceof Date ? b['_sortDate'].getTime() : 0;
      return dB - dA;
    };
    return { 
      success: true, 
      data: activeTasks.sort(dateSorter).map(({_sortDate, ...rest}) => rest), 
      history: historyTasks.sort(dateSorter).map(({_sortDate, ...rest}) => rest), 
      headers: cleanHeaders 
    };
  } catch (e) { return { success: false, message: e.toString() }; }
}

function apiFetchStaffTrackerData(personName) {
  return internalFetchSheetData(personName);
}

function apiFetchSalesHistory() {
  try {
    const dataRes = internalFetchSheetData(APP_CONFIG.salesSheetName);
    if (!dataRes.success) return dataRes;
    const allData = [...dataRes.data, ...dataRes.history];
    const grouped = {};
    
    allData.forEach(row => {
        const vendedorKey = Object.keys(row).find(k => k.toUpperCase().includes("VENDEDOR"));
        const clienteKey = Object.keys(row).find(k => k.toUpperCase().includes("CLIENTE"));
        const descKey = Object.keys(row).find(k => k.toUpperCase().includes("CONCEPTO"));
        const statusKey = Object.keys(row).find(k => k.toUpperCase().includes("ESTATUS"));
        const dateKey = Object.keys(row).find(k => k.toUpperCase().includes("FECHA"));

        if (vendedorKey && row[vendedorKey]) {
            const name = String(row[vendedorKey]).trim().toUpperCase();
            if (!grouped[name]) grouped[name] = [];
            
            let pulse = 0;
            const status = String(row[statusKey] || "").toUpperCase();
            if (status.includes("VENDIDA") || status.includes("APROBADA") || status.includes("GANADA")) pulse = 10;
            else if (status.includes("COTIZADA") || status.includes("ENVIADA")) pulse = 5;
            else if (status.includes("PERDIDA") || status.includes("CANCELADA")) pulse = -5;
            else pulse = 1;

            grouped[name].push({
                client: row[clienteKey] || "S/C",
                desc: row[descKey] || "",
                status: status,
                date: row[dateKey] || "",
                pulse: pulse,
                displayDate: row[dateKey] ? String(row[dateKey]).substring(0,5) : ""
            });
        }
    });

    return { success: true, data: grouped };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/**
 * ======================================================================
 * OPTIMIZACIÓN SCRIPTMASTER V153: PROTOCOLO ANTI-BLOQUEO (FILTROS)
 * ======================================================================
 */
function internalBatchUpdateTasks(sheetName, tasksArray, useOwnLock = true, options = {}) {
  if (!tasksArray || tasksArray.length === 0) return { success: true, data: [] };
  const opts = options || {};
  const lock = LockService.getScriptLock();
  if (useOwnLock) {
    if (!lock.tryLock(10000)) {
        return { success: false, message: "Hoja ocupada, intenta de nuevo."};
    }
  }
  
  try {
    const sheet = findSheetSmart(sheetName);
    if (!sheet) return { success: false, message: "Hoja no encontrada: " + sheetName };
    const dataRange = sheet.getDataRange();
    let values = dataRange.getValues();
    if (values.length === 0) return { success: false, message: "Hoja vacía" };
    
    const headerRowIndex = findHeaderRow(values);
    if (headerRowIndex === -1) return { success: false, message: "Sin cabeceras válidas" };
    // 1. SANITIZAR HEADERS Y ELIMINAR FILTROS ROTOS (FIX CRÍTICO)
    let headersChanged = false;
    for(let c = 0; c < values[headerRowIndex].length; c++) {
        if (values[headerRowIndex][c] === "" || values[headerRowIndex][c] === null) {
            values[headerRowIndex][c] = "COL_" + (c + 1);
            headersChanged = true;
        }
    }

    if (headersChanged) {
        const existingFilter = sheet.getFilter();
        if (existingFilter) {
            try { existingFilter.remove(); } catch(e) {} 
        }
        sheet.getRange(headerRowIndex + 1, 1, 1, values[headerRowIndex].length).setValues([values[headerRowIndex]]);
        SpreadsheetApp.flush(); 
    }

    // FIX: HEADERS CON SALTOS DE LINEA (NORMALIZACIÓN ROBUSTA)
    const headers = values[headerRowIndex].map(h => String(h).toUpperCase().replace(/\n/g, ' ').replace(/\s+/g, ' ').trim());
    const maxCols = values.reduce((max, r) => Math.max(max, r.length), 0);
    const totalColumns = Math.max(maxCols, headers.length);

    const colMap = {};
    headers.forEach((h, i) => colMap[h] = i);
    const getColIdx = (key) => {
      const k = key.toUpperCase().trim();
      if (colMap[k] !== undefined) return colMap[k];
      const aliases = {
        'FECHA': ['FECHA', 'FECHAS', 'FECHA ALTA', 'FECHA INICIO', 'ALTA', 'FECHA DE INICIO', 'FECHA VISITA', 'FECHA DE ALTA', 'F_INICIO'],
        'CONCEPTO': ['CONCEPTO', 'DESCRIPCION', 'DESCRIPCIÓN DE LA ACTIVIDAD', 'DESCRIPCIÓN', 'ACTIVIDAD'],
        'RESPONSABLE': ['RESPONSABLE', 'RESPONSABLES', 'INVOLUCRADOS', 'VENDEDOR', 'ENCARGADO', 'ASIGNADO'],
        'RELOJ': ['RELOJ', 'HORAS', 'DIAS', 'DÍAS'],
        'ESTATUS': ['ESTATUS', 'STATUS'],
        'CUMPLIMIENTO': ['CUMPLIMIENTO', 'CUMPL.', 'CUMP'],
        'AVANCE': ['AVANCE', 'AVANCE %', '% AVANCE'],
        'ALTA': ['AREA', 'DEPARTAMENTO', 'ESPECIALIDAD', 'ALTA'],
        'FECHA_RESPUESTA': ['FECHA RESPUESTA', 'FECHA FIN', 'FECHA ESTIMADA DE FIN', 'FECHA ESTIMADA', 'FECHA DE ENTREGA', 'FECHA_FIN', 'DEADLINE'],
        'PRIORIDAD': ['PRIORIDAD', 'PRIORIDADES'],
        'RIESGOS': ['RIESGO', 'RIESGOS'],
        'ARCHIVO': ['ARCHIVO', 'ARCHIVOS', 'CLIP', 'LINK', 'URL', 'EVIDENCIA', 'DOCUMENTO', 'FOTO', 'VIDEO'],
        'CLASIFICACION': ['CLASIFICACION', 'CLASI'],
        'COMENTARIOS': ['COMENTARIOS', 'COMENTARIO', 'COMENTARIOS SEMANA EN CURSO', 'OBSERVACIONES', 'NOTAS', 'DETALLES'],
        'PREVIOS': ['COMENTARIOS PREVIOS', 'PREVIOS', 'COMENTARIOS SEMANA PREVIA'],
        'FECHA_TERMINO': ['FECHA TERMINO', 'FECHA REAL', 'TERMINO', 'REALIZADO']
      };
      for (let main in aliases) {
        if (aliases[main].includes(k)) {
             for(let alias of aliases[main]) if(colMap[alias] !== undefined) return colMap[alias];
        }
      }
      return -1;
    };
    const folioIdx = getColIdx('FOLIO') > -1 ? getColIdx('FOLIO') : getColIdx('ID');
    let rowsToAppend = [];
    let singleRowIndex = -1;
    let modified = false;

    // GATEKEEPER: candado por _tempId para bloquear inserciones concurrentes
    // del mismo evento de UI (AGENTS.md §2 "Gatekeeper con CacheService").
    let gkCache = null;
    try { gkCache = CacheService.getScriptCache(); } catch (e) { gkCache = null; }
    const gkKeyFor = (tempId) => 'GK_' + String(sheetName).toUpperCase().trim() + '_' + String(tempId);

    // Busca una fila por FOLIO dentro de la matriz en memoria.
    const findRowByFolio = (folio) => {
      if (folioIdx === -1 || !folio) return -1;
      const target = String(folio).toUpperCase().trim();
      for (let i = headerRowIndex + 1; i < values.length; i++) {
        if (String(values[i][folioIdx]).toUpperCase().trim() === target) return i;
      }
      return -1;
    };

    // FALLBACK ROBUSTO (AGENTS.md §2 "Resolución de Conflictos"):
    // si el FOLIO no existe o se perdió, la fila se identifica por la
    // combinación CONCEPTO + FECHA (+ RESPONSABLE cuando viene en el payload).
    const conceptoIdx = getColIdx('CONCEPTO');
    const fechaIdx = getColIdx('FECHA');
    const responsableIdx = getColIdx('RESPONSABLE');
    const findRowByFingerprint = (task) => {
      if (conceptoIdx === -1 || fechaIdx === -1) return -1;
      const tConcepto = normalizeCellValue(pickTaskValue(task, ['CONCEPTO', 'DESCRIPCION', 'DESCRIPCIÓN', 'ACTIVIDAD']));
      const tFecha = normalizeCellValue(pickTaskValue(task, ['FECHA', 'FECHA ALTA', 'ALTA', 'FECHA INICIO', 'FECHA DE INICIO']));
      if (!tConcepto || !tFecha) return -1;
      const tResp = normalizeCellValue(pickTaskValue(task, ['RESPONSABLE', 'INVOLUCRADOS', 'VENDEDOR', 'ENCARGADO', 'ASIGNADO']));
      for (let i = headerRowIndex + 1; i < values.length; i++) {
        const row = values[i];
        if (normalizeCellValue(row[conceptoIdx]) !== tConcepto) continue;
        if (normalizeCellValue(row[fechaIdx]) !== tFecha) continue;
        if (tResp && responsableIdx > -1) {
          const rowResp = normalizeCellValue(row[responsableIdx]);
          if (rowResp && rowResp !== tResp) continue;
        }
        return i;
      }
      return -1;
    };

    const notifyQueue = [];

    // 2. Procesar Tareas
    tasksArray.forEach(task => {
      let rowIndex = -1;

      const tFolio = String(task['FOLIO'] || task['ID'] || "").toUpperCase().trim();

      if (task._rowIndex) {
        const candidateRowIndex = parseInt(task._rowIndex) - 1;
        // 2.1 VALIDACIÓN DE SEGURIDAD (ANTI-DESPLAZAMIENTO)
        // Verificamos que el Folio en esa fila coincida con el payload.
        // Si hubo movimientos (filas borradas/insertadas), el índice ya no coincidirá.
        if (candidateRowIndex > headerRowIndex && candidateRowIndex < values.length && folioIdx > -1 && tFolio) {
             const rowFolio = String(values[candidateRowIndex][folioIdx] || "").toUpperCase().trim();
             if (rowFolio === tFolio) {
                 rowIndex = candidateRowIndex;
             } else {
                 console.warn(`[SYNC WARNING] Desplazamiento detectado. Folio Payload: ${tFolio} vs Folio Fila: ${rowFolio} (Fila ${candidateRowIndex+1}). Activando búsqueda.`);
             }
        } else if (!tFolio) {
             // Si no hay folio (ej. solo fila), confiamos en el índice si es válido
             if (candidateRowIndex > headerRowIndex && candidateRowIndex < values.length) rowIndex = candidateRowIndex;
        }
      }

      if (rowIndex === -1 && tFolio && folioIdx > -1) {
           // Búsqueda Robusta por Folio
           rowIndex = findRowByFolio(tFolio);
      }

      // GATEKEEPER: si esta misma petición (mismo _tempId) ya insertó la fila,
      // recuperamos el folio que se le asignó en lugar de crear un duplicado.
      const tempId = task._tempId ? String(task._tempId).trim() : "";
      let gkKey = "";
      let gkAlreadyProcessed = false;
      if (tempId && gkCache) {
        gkKey = gkKeyFor(tempId);
        try {
          const cachedFolio = gkCache.get(gkKey);
          if (cachedFolio) {
            gkAlreadyProcessed = true;
            if (rowIndex === -1) rowIndex = findRowByFolio(cachedFolio);
          }
        } catch (e) { /* el cache nunca debe bloquear el guardado */ }
      }

      // FALLBACK: recuperación de la fila por CONCEPTO + FECHA + RESPONSABLE
      if (rowIndex === -1) {
        rowIndex = findRowByFingerprint(task);
      }

      if (rowIndex > -1 && rowIndex < values.length) {
         Object.keys(task).forEach(key => {
            if (key.startsWith('_')) return;
            const cIdx = getColIdx(key);
            if (cIdx > -1) values[rowIndex][cIdx] = task[key];
        });
        // Fila reparada sin folio: se le asigna uno nuevo sin dañar su historial.
        if (folioIdx > -1) {
          if (!String(values[rowIndex][folioIdx] || "").trim()) {
            values[rowIndex][folioIdx] = generateFolioForSheet(sheetName);
          }
          task['FOLIO'] = values[rowIndex][folioIdx];
        }
        task._rowIndex = rowIndex + 1;
        if (gkKey && gkCache) {
          try { gkCache.put(gkKey, String(task['FOLIO'] || ""), 600); } catch (e) { }
        }
        singleRowIndex = rowIndex;
        modified = true;
      }
      else if (gkAlreadyProcessed) {
        // Petición duplicada cuya fila aún no es visible: se descarta.
        console.warn(`[GATEKEEPER] Petición duplicada ignorada (_tempId=${tempId}) en ${sheetName}`);
      }
      else {
          // BATCH DEDUP: Check if already appending this ID in current batch
          let appendedRowIndex = -1;
          const tFolio = String(task['FOLIO'] || task['ID'] || "").toUpperCase().trim();

          if (folioIdx > -1 && tFolio) {
               for(let k=0; k<rowsToAppend.length; k++) {
                   if(String(rowsToAppend[k][folioIdx]).toUpperCase().trim() === tFolio) {
                       appendedRowIndex = k;
                       break;
                   }
               }
          }

          if (appendedRowIndex > -1) {
              // Update the pending row instead of creating duplicate
              const targetRow = rowsToAppend[appendedRowIndex];
              Object.keys(task).forEach(key => {
                  if (key.startsWith('_')) return;
                  const cIdx = getColIdx(key);
                  if (cIdx > -1) targetRow[cIdx] = task[key];
              });
          } else {
              const newRow = new Array(totalColumns).fill("");
              Object.keys(task).forEach(key => {
                  if (key.startsWith('_')) return;
                  const cIdx = getColIdx(key);
                  if (cIdx > -1) newRow[cIdx] = task[key];
              });
              if (folioIdx > -1 && !newRow[folioIdx]) {
                  const provided = pickTaskValue(task, ['FOLIO', 'ID']);
                  // Folio con prefijo del titular de la hoja (JO-, JC-, AV-, AP-, ...)
                  newRow[folioIdx] = provided ? provided : generateFolioForSheet(sheetName);
              }
              if (folioIdx > -1) task['FOLIO'] = newRow[folioIdx];
              const statusIdx = getColIdx('ESTATUS');
              if(statusIdx > -1 && !newRow[statusIdx]) newRow[statusIdx] = 'ASIGNADO';
              if (gkKey && gkCache) {
                  try { gkCache.put(gkKey, String(task['FOLIO'] || ""), 600); } catch (e) { }
              }
              if (!opts.skipNotify && shouldNotifySheet(sheetName)) notifyQueue.push(task);
              rowsToAppend.push(newRow);
          }
      }
    });
    // 3. AUTO-ARCHIVADO
    let rowsMoved = false;
    const avanceIdx = getColIdx('AVANCE');
    const fechaTerminoIdx = getColIdx('FECHA_TERMINO');
    const estatusArchIdx = getColIdx('ESTATUS');
    const cumplimientoIdx = getColIdx('CUMPLIMIENTO');

    if (avanceIdx > -1 || estatusArchIdx > -1 || cumplimientoIdx > -1) {
        let separatorIndex = -1;
        for(let i=0; i<values.length; i++) {
            if(String(values[i][0]).toUpperCase().includes("TAREAS REALIZADAS") || 
               String(values[i].join("|")).toUpperCase().includes("TAREAS REALIZADAS")) { 
                separatorIndex = i;
                break;
            }
        }

        let headerAndTop = values.slice(0, headerRowIndex + 1);
        let activeRows = [];
        let separatorRow = [];
        let historyRows = [];
        if (separatorIndex === -1) {
            activeRows = values.slice(headerRowIndex + 1);
        } else {
            activeRows = values.slice(headerRowIndex + 1, separatorIndex);
            separatorRow = [values[separatorIndex]];
            historyRows = values.slice(separatorIndex + 1);
        }

        const newActiveRows = [];
        const movedRows = [];
        
        activeRows.forEach(row => {
            // CRITERIOS DE CIERRE (AGENTS.md §4):
            //  - AVANCE al 100 % ("100", "100%", "100,0" o el número nativo 1
            //    de una celda con formato porcentaje; el string "1" es 1 %).
            //  - ESTATUS terminal (HECHO / DONE / GANADA / PERDIDA X ...).
            //  - CUMPLIMIENTO = SI.
            let isComplete = false;
            if (avanceIdx > -1 && isProgressComplete(row[avanceIdx])) isComplete = true;
            if (!isComplete && estatusArchIdx > -1 && isTerminalStatus(row[estatusArchIdx])) isComplete = true;
            if (!isComplete && cumplimientoIdx > -1 &&
                String(row[cumplimientoIdx] || "").toUpperCase().trim() === "SI") isComplete = true;

            if (isComplete) {
                // AUTO-TIMESTAMP: FECHA TERMINO REAL
                if (fechaTerminoIdx > -1) {
                   if (!row[fechaTerminoIdx]) {
                       row[fechaTerminoIdx] = Utilities.formatDate(new Date(), SS.getSpreadsheetTimeZone(), "dd/MM/yy");
                   }
                }
                movedRows.push(row);
                rowsMoved = true;
            } else {
                newActiveRows.push(row);
            }
        });
        if (rowsMoved || (rowsToAppend.length > 0 && separatorIndex === -1)) {
            if (separatorRow.length === 0) {
                const sep = new Array(totalColumns).fill("");
                const titleCol = totalColumns > 2 ? 2 : 0; 
                sep[titleCol] = "TAREAS REALIZADAS";
                separatorRow = [sep];
            }
            values = [ ...headerAndTop, ...rowsToAppend, ...newActiveRows, ...separatorRow, ...movedRows, ...historyRows ];
            rowsToAppend = []; 
            modified = true;
            singleRowIndex = -1;
        }
    }

    // 4. ESCRITURA BLINDADA
    if (modified) {
       const finalMaxCols = values.reduce((max, r) => Math.max(max, r.length), totalColumns);
       const normalizedValues = values.map(r => {
           if (r.length === finalMaxCols) return r;
           const diff = finalMaxCols - r.length;
           return r.concat(new Array(diff).fill(""));
       });
       if (tasksArray.length === 1 && singleRowIndex > -1 && !rowsMoved) {
          let singleRow = values[singleRowIndex];
          if(singleRow.length < finalMaxCols) {
               singleRow = singleRow.concat(new Array(finalMaxCols - singleRow.length).fill(""));
          }
          sheet.getRange(singleRowIndex + 1, 1, 1, finalMaxCols).setValues([singleRow]);
       } else {
          // REMOVE FILTER IF EXISTS TO AVOID "HEADER MUST HAVE VALUE" ERROR
          const existingFilter = sheet.getFilter();
          if (existingFilter) {
              try { existingFilter.remove(); } catch(e) {}
          }

          if(values.length < dataRange.getNumRows()) sheet.clearContents();
          if(headerRowIndex < normalizedValues.length) {
              for(let c=0; c<normalizedValues[headerRowIndex].length; c++){
                  if(!normalizedValues[headerRowIndex][c]) normalizedValues[headerRowIndex][c] = "COL_" + (c+1);
              }
          }
          sheet.getRange(1, 1, normalizedValues.length, finalMaxCols).setValues(normalizedValues);
       }
    }

    if (rowsToAppend.length > 0) {
        const finalMaxCols = values.length > 0 ? values[0].length : totalColumns;
        const normalizedAppend = rowsToAppend.map(r => {
             if (r.length >= finalMaxCols) return r;
             return r.concat(new Array(finalMaxCols - r.length).fill(""));
        });
        const insertPos = headerRowIndex + 2;
        sheet.insertRowsBefore(insertPos, rowsToAppend.length);
        sheet.getRange(insertPos, 1, normalizedAppend.length, finalMaxCols).setValues(normalizedAppend);

        // 5. AUTO-HEALING: FORMATO CONDICIONAL (SEMAFORO)
        // Se ejecuta solo al crear nuevas tareas para garantizar que el rango cubra la nueva fila superior.
        const excludedForFormatting = [APP_CONFIG.logSheetName, APP_CONFIG.draftSheetName, APP_CONFIG.salesSheetName, "DB_SITIOS", "DB_PROYECTOS", "DB_DIRECTORY"];
        if (!excludedForFormatting.includes(sheetName) && !sheetName.startsWith("DB_")) {
             try { applyTrafficLightToSheet(sheet); } catch(e) { console.warn("Auto-Format Error: " + e.toString()); }
        }
    }
    
    SpreadsheetApp.flush();

    // 5-bis. ESPEJO EN SUPABASE (nunca bloquea el guardado)
    // Va después del flush: Sheets ya es la fuente de verdad y esto solo
    // replica. Si Supabase falla, se registra y la operación continúa.
    try { SupabaseSync.mirrorBatch(sheetName, tasksArray); }
    catch (e) { console.warn("Espejo Supabase fallido: " + e.toString()); }

    // 6. NOTIFICACIÓN MAKE.COM -> OUTLOOK (nunca bloquea el guardado)
    if (notifyQueue.length > 0) {
        notifyQueue.forEach(task => {
            try { NotifierService.notifyAssignment(sheetName, task); }
            catch (e) { console.warn("Notificación fallida: " + e.toString()); }
        });
    }

    // AGENTS.md §2: el backend devuelve el objeto completo en res.data para que
    // el frontend lo fusione y marque _isNew = false.
    return { success: true, moved: rowsMoved, data: tasksArray };
  } catch (e) {
    console.error(e);
    return { success: false, message: e.toString() };
  } finally {
    if (useOwnLock) lock.releaseLock();
  }
}

function apiUpdatePPCV3(taskData, username) {
  // Ensure backward compatibility with sheet headers
  if (taskData['COMENTARIOS SEMANA EN CURSO'] !== undefined) taskData['COMENTARIOS'] = taskData['COMENTARIOS SEMANA EN CURSO'];
  if (taskData['COMENTARIOS SEMANA PREVIA'] !== undefined) taskData['COMENTARIOS PREVIOS'] = taskData['COMENTARIOS SEMANA PREVIA'];

  const targetSheet = (String(username).toUpperCase().trim() === 'ANTONIA_VENTAS') ? 'PPCV4' : APP_CONFIG.ppcSheetName;

  // EXPLICIT REMAPPING FOR PPCV4 (TOÑITA) TO MATCH SCREENSHOT HEADERS EXACTLY
  if (targetSheet === 'PPCV4') {
      if (taskData['FECHA']) taskData['Fecha de Alta'] = taskData['FECHA'];
      if (taskData['CONCEPTO']) taskData['Descripción de la Actividad'] = taskData['CONCEPTO'];
      if (taskData['ARCHIVO']) taskData['Archivos'] = taskData['ARCHIVO'];
      // Keep original keys too, internalBatchUpdateTasks will handle duplicates/aliases, but explicit keys take precedence in matching
  }

  const res = internalBatchUpdateTasks(targetSheet, [taskData]);
  if(res.success) {
      const action = (taskData['COMENTARIOS'] || taskData['comentarios']) ? "ACTUALIZAR/COMENTARIO" : "ACTUALIZAR";
      registrarLog(username || "DESCONOCIDO", action, `Update ${targetSheet} ID: ${taskData['ID']||taskData['FOLIO']}`);
  }
  return res;
}

function internalUpdateTask(personName, taskData, username) {
    try {
        // GUARD: PPCV3 Inmutabilidad (Solo modificable por Weekly Plan)
        if (String(personName).trim().toUpperCase() === String(APP_CONFIG.ppcSheetName).trim().toUpperCase()) {
            return { success: false, message: "Operación no permitida: PPCV3 es de solo lectura desde esta vista." };
        }

        // RUTEO PROTEGIDO DE VENTAS ("La Ley de Antonia", AGENTS.md §3):
        // se purga el sufijo (VENTAS) a usuarios ajenos y se blinda el core de Toñita.
        const routing = resolveTrackerTarget(personName, username);
        if (routing.redirected) {
            registrarLog(username || "DESCONOCIDO", "RUTEO_PROTEGIDO",
                `${personName} -> ${routing.sheet} (${routing.reason})`);
        }
        personName = routing.sheet;

        const isAntonia = String(personName).toUpperCase() === "ANTONIA_VENTAS";

        // --- NEW RESTRICTION BLOCK (ANGEL, TERESA, EDUARDO, MANZANARES, RAMIRO, SEBASTIAN, EDGAR) ---
        const restrictedUsers = ["ANGEL_SALINAS", "TERESA_GARZA", "EDUARDO_TERAN", "EDUARDO_MANZANARES", "RAMIRO_RODRIGUEZ", "SEBASTIAN_PADILLA", "EDGAR_LOPEZ"];
        if (restrictedUsers.includes(String(username).toUpperCase().trim())) {
             const allowed = ['FOLIO', 'ID', 'AVANCE', 'AVANCE %', 'REQUISITOR', 'INFO CLIENTE', 'F2', 'COTIZACION', 'COT', 'TIMELINE', 'LAYOUT', '_rowIndex'];
             // Helper to check if key matches allowed
             const isAllowed = (k) => {
                 const kUp = k.toUpperCase();
                 if (k.startsWith('_')) return true;
                 return allowed.some(a => kUp.includes(a));
             };

             Object.keys(taskData).forEach(key => {
                 if (!isAllowed(key)) {
                     delete taskData[key];
                 }
             });
        }
        // --- END NEW RESTRICTION BLOCK ---

        // DISTRIBUCIÓN LATERAL ("Papa Caliente"): calcula PROCESO_LOG y MAP COT
        // antes de escribir la maestra, y delega la fase a cada trabajador.
        let hotPotato = null;
        if (isAntonia) {
            hotPotato = internalApplyHotPotato(personName, taskData, username);
        }

        if (isAntonia) {
             // 1. AUTO-INCREMENT FOLIO (Before Saving)
             if (!taskData['FOLIO'] && !taskData['ID']) {
                 // NEW TASK -> GENERATE ID (con prefijo AV- del core de ventas)
                 taskData['FOLIO'] = generateFolioForSheet(personName);
             } else {
                 // 2. EXISTING TASK -> APPLY RESTRICTIONS (User Request)
                 // "Una vez que guarde... los únicos datos que pueda modificar es FECHA VISITA, ESTATUS y AVANCE"

                 const allowedBase = ['FOLIO', 'ID', 'ESTATUS', 'STATUS', 'AVANCE', 'AVANCE %', '_rowIndex', 'VENDEDOR', 'RESPONSABLE', 'INVOLUCRADOS', 'ENCARGADO', 'CONCEPTO', 'DESCRIPCION', 'CLIENTE', 'COTIZACION', 'F2', 'LAYOUT', 'TIMELINE', 'AREA', 'CLASIFICACION', 'CLASI', 'DIAS', 'RELOJ', 'ESPECIALIDAD',
                     // Timeline de la Papa Caliente (delegación de fases)
                     'PROCESO', 'PROCESO_LOG', 'MAP COT', 'ETAPA', 'FASE'];

                 Object.keys(taskData).forEach(key => {
                     const kUp = key.toUpperCase();
                     if (key.startsWith('_')) return; // Preserve internal keys

                     const isBase = allowedBase.includes(kUp);
                     const isDate = kUp.includes('FECHA') || kUp.includes('ALTA'); // Allow Date fields

                     if (!isBase && !isDate) {
                         delete taskData[key];
                     }
                 });
             }
        }

        const res = internalBatchUpdateTasks(personName, [taskData]);

        if (res.success && username) {
             const action = (taskData['COMENTARIOS'] || taskData['comentarios'] || taskData['COMENTARIOS SEMANA EN CURSO']) ? "ACTUALIZAR/COMENTARIO" : "ACTUALIZAR";
             registrarLog(username, action, `Update Task ID: ${taskData['ID']||taskData['FOLIO']} en ${personName}`);
        }

        if (isAntonia) {
             const distData = JSON.parse(JSON.stringify(taskData));
             delete distData._rowIndex; 

             // MODIFICADO: Se comenta la distribución a vendedores para evitar duplicidad y tráfico innecesario.
             // "ya no mandará la misma tarea a la hoja de los vendedores"
             // UPDATE: Se reactiva la distribución por reporte de bug (No se reflejaban actividades).

             const vendedorKey = Object.keys(taskData).find(k => k.toUpperCase().trim() === "VENDEDOR");
             if (vendedorKey && taskData[vendedorKey]) {
                 const vendedorName = String(taskData[vendedorKey]).trim();
                 if (vendedorName.toUpperCase() !== "ANTONIA_VENTAS") {
                     try { 
                        // TRAFFIC SPLITTING REFACTORIZADO
                        let targetSheet = vendedorName;
                        let hasSuffix = targetSheet.toUpperCase().includes("(VENTAS)");
                        let finalTarget = null;

                        if (hasSuffix) {
                            finalTarget = targetSheet;
                        } else {
                            let potentialSheet = targetSheet + " (VENTAS)";
                            if (findSheetSmart(potentialSheet)) {
                                finalTarget = potentialSheet;
                            }
                        }

                        if (finalTarget) {
                             const vRes = internalBatchUpdateTasks(finalTarget, [distData]);
                             if(!vRes.success) registrarLog("ANTONIA", "DIST_FAIL", "Fallo copia a " + finalTarget + ": " + vRes.message);
                        } else {
                             registrarLog("ANTONIA", "DIST_SKIP", "Omitido " + vendedorName + " - No se encontró tabla (VENTAS).");
                        }
                     } catch(e){
                        registrarLog("ANTONIA", "DIST_ERROR", e.toString());
                     }
                 }
             }

             try { internalBatchUpdateTasks("ADMINISTRADOR", [distData]); } catch(e){}
        } else if (String(personName).toUpperCase().includes("(VENTAS)")) {
             // Sincronización Inversa: Vendedor -> ANTONIA_VENTAS.
             // internalReverseSyncToAntonia purga ESTATUS/AVANCE/CUMPLIMIENTO para que
             // una fase parcial no cierre la venta global, y actualiza el timeline.
             try {
                 const syncData = JSON.parse(JSON.stringify(taskData));
                 delete syncData._rowIndex; // Evitar conflictos de índice de fila
                 internalReverseSyncToAntonia(personName, [syncData], username);
             } catch (e) {
                 console.error("Error en sincronización inversa: " + e.toString());
             }
        }
        // RETURN UPDATED DATA (Critical for Frontend Folio Update)
        res.data = taskData;
        if (hotPotato) res.hotPotato = hotPotato;
        if (routing.redirected) res.routing = routing;
        return res;
    } catch(e) { return {success:false, message:e.toString()}; }
}

function apiUpdateTask(personName, taskData, username) {
  return internalUpdateTask(personName, taskData, username);
}

function apiFetchDrafts() {
  try {
    const sheet = findSheetSmart(APP_CONFIG.draftSheetName);
    if (!sheet) return { success: true, data: [] };
    const rows = sheet.getDataRange().getValues();
    if (rows.length < 1) return { success: true, data: [] }; 
    const startRow = (rows[0][0] === "ESPECIALIDAD") ? 1 : 0;
    const drafts = rows.slice(startRow).map(r => ({
      especialidad: r[0], concepto: r[1], responsable: r[2], horas: r[3], cumplimiento: r[4],
      archivoUrl: r[5], comentarios: r[6], comentariosPrevios: r[7], 
      prioridades: r[8], riesgos: r[9], restricciones: r[10], fechaRespuesta: r[11], 
      clasificacion: r[12], fechaAlta: r[13] 
    })).filter(d => d.concepto);
    return { success: true, data: drafts };
  } catch(e) { return { success: false, message: e.toString() };
  }
}

function apiSyncDrafts(drafts) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(5000)) {
    try {
      let sheet = findSheetSmart(APP_CONFIG.draftSheetName);
      if (!sheet) { sheet = SS.insertSheet(APP_CONFIG.draftSheetName); }
      sheet.clear();
      const headers = ["ESPECIALIDAD", "CONCEPTO", "RESPONSABLE", "HORAS", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "PREVIOS", "PRIORIDAD", "RIESGOS", "RESTRICCIONES", "FECHA_RESP", "CLASIFICACION", "FECHA_ALTA"];
      if (drafts && drafts.length > 0) {
        const rows = drafts.map(d => [
          d.especialidad || "", d.concepto || "", d.responsable || "", d.horas || "", d.cumplimiento || "NO",
          d.archivoUrl || "", d.comentarios || "", d.comentariosPrevios || "",
          d.prioridades || "", d.riesgos || "", d.restricciones || "", d.fechaRespuesta || "", 
          d.clasificacion || "", d.fechaAlta || new Date() 
        ]);
        sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
        sheet.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
      } else {
        sheet.appendRow(headers);
      }
      return { success: true };
    } catch(e) { return { success: false, message: e.toString() }; } finally { lock.releaseLock();
    }
  }
  return { success: false, message: "Ocupado syncing drafts" };
}

function apiClearDrafts() {
  try {
    const sheet = findSheetSmart(APP_CONFIG.draftSheetName);
    if(sheet) sheet.clear();
    return { success: true };
  } catch(e) { return { success: false }; }
}

function ensureSheetWithHeaders(sheetName, headers) {
    let sheet = findSheetSmart(sheetName);
    if (!sheet) {
        sheet = SS.insertSheet(sheetName);
        sheet.appendRow(headers);
        // Formato básico
        sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#e6e6e6");
    }
    return sheet;
}

function saveChildData(sheetName, items, headers) {
    if (!items || items.length === 0) return;
    const sheet = ensureSheetWithHeaders(sheetName, headers);

    // Convertir objetos a array basado en headers
    const rows = items.map(item => {
        return headers.map(h => item[h] || item[h.replace(" ", "_")] || "");
    });

    // Append rows (BATCH)
    if (rows.length > 0) {
        sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
    }
}

function apiSavePPCData(payload, activeUser) {
  const lock = LockService.getScriptLock();
  // Esperar hasta 30 segundos para obtener el candado y evitar condiciones de carrera
  if (lock.tryLock(30000)) {
    try {
      const items = Array.isArray(payload) ? payload : [payload];
      
      // 1. VERIFICACIÓN CRÍTICA DE PPCV3
      let sheetPPC = findSheetSmart(APP_CONFIG.ppcSheetName);
      if (!sheetPPC) { 
        sheetPPC = SS.insertSheet(APP_CONFIG.ppcSheetName);
        // Standardize headers for robustness
        sheetPPC.appendRow(["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA"]);
      }

      // 1.1 VERIFICACIÓN CRÍTICA DE PPCV4 (Para ANTONIA_VENTAS)
      if (String(activeUser).toUpperCase().trim() === 'ANTONIA_VENTAS') {
          let sheetPPC4 = findSheetSmart('PPCV4');
          if (!sheetPPC4) {
             sheetPPC4 = SS.insertSheet('PPCV4');
             sheetPPC4.appendRow(["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA"]);
          }
      }
      
      const fechaHoy = new Date();
      const fechaStr = Utilities.formatDate(fechaHoy, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
      
      // Estructuras para Batch Operations
      const tasksBySheet = {};
      const logEntries = [];
      const generatedIds = [];

      const addTaskToSheet = (sheetName, task) => {
          if (!sheetName) return;
          const key = sheetName.trim();
          if (!tasksBySheet[key]) tasksBySheet[key] = [];
          tasksBySheet[key].push(task);
      };

      // 2. PREPARACIÓN DE DATOS EN MEMORIA
      items.forEach(item => {
          // Use existing ID if provided (for updates/tests) or generate new
          let id = item.id;
          if (!id) {
              if (activeUser === 'PREWORK_ORDER') {
                  id = generateWorkOrderFolio(item.cliente, item.especialidad);
              } else {
                  id = "PPC-" + Math.floor(Math.random() * 1000000);
              }
          }
          generatedIds.push(id);
          const comentarios = item.comentarios || "";

          // --- NUEVO: GUARDADO DE DETALLES EN HOJAS HIJAS ---
          // A. Materiales
          if (item.materiales && item.materiales.length > 0) {
             const matItems = item.materiales.map(m => ({
                 FOLIO: id, ...m,
                 RESIDENTE: m.papaCaliente ? m.papaCaliente.residente : "",
                 COMPRAS: m.papaCaliente ? m.papaCaliente.compras : "",
                 CONTROLLER: m.papaCaliente ? m.papaCaliente.controller : "",
                 ORDEN_COMPRA: m.papaCaliente ? m.papaCaliente.ordenCompra : "",
                 PAGOS: m.papaCaliente ? m.papaCaliente.pagos : "",
                 ALMACEN: m.papaCaliente ? m.papaCaliente.almacen : "",
                 LOGISTICA: m.papaCaliente ? m.papaCaliente.logistica : "",
                 RESIDENTE_OBRA: m.papaCaliente ? m.papaCaliente.residenteObra : ""
             }));
             saveChildData(APP_CONFIG.woMaterialsSheet, matItems, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"]);
          }

          // B. Mano de Obra
          if (item.manoObra && item.manoObra.length > 0) {
             const laborItems = item.manoObra.map(l => ({ FOLIO: id, UNIDAD: l.unit || "", ...l }));
             saveChildData(APP_CONFIG.woLaborSheet, laborItems, ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "UNIDAD", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "TOTAL"]);
          }

          // C. Herramientas
          if (item.herramientas && item.herramientas.length > 0) {
             const toolItems = item.herramientas.map(t => ({
                 FOLIO: id, ...t,
                 RESIDENTE: t.papaCaliente ? t.papaCaliente.residente : "",
                 CONTROLLER: t.papaCaliente ? t.papaCaliente.controller : "",
                 ALMACEN: t.papaCaliente ? t.papaCaliente.almacen : "",
                 LOGISTICA: t.papaCaliente ? t.papaCaliente.logistica : "",
                 RESIDENTE_FIN: t.papaCaliente ? t.papaCaliente.residenteFin : ""
             }));
             saveChildData(APP_CONFIG.woToolsSheet, toolItems, ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"]);
          }

          // D. Equipos
          if (item.equipos && item.equipos.length > 0) {
             const eqItems = item.equipos.map(e => ({ FOLIO: id, ...e }));
             saveChildData(APP_CONFIG.woEquipSheet, eqItems, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"]);
          }

          // E. Programa
          if (item.programa && item.programa.length > 0) {
             const progItems = item.programa.map(p => ({
                 FOLIO: id,
                 ...p,
                 FECHA_INICIO: p.fechaInicio || "",
                 FECHA_ENTREGA: p.fechaEntrega || "",
                 ARCHIVO: p.fileUrl || "",
                 SECCION: p.seccion || "",
                 ESTATUS: p.checkStatus || (p.isActive ? 'APPLY' : 'PENDING')
             }));
             saveChildData(APP_CONFIG.woProgramSheet, progItems, ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "FECHA_INICIO", "FECHA_ENTREGA", "ARCHIVO", "SECCION", "ESTATUS"]);
          }

          // F. Detalles Extra (Checklist, Costos Adicionales) - JSON
          let detallesExtra = "";
          if (item.checkList || item.additionalCosts) {
              detallesExtra = JSON.stringify({
                  checkList: item.checkList,
                  costs: item.additionalCosts
              });
          }

          // Mapeo Explícito para PPCV3
          const taskData = {
                 'FOLIO': id,
                 'CONCEPTO': item.concepto,
                 'CLASIFICACION': item.clasificacion || "Media",
                 'AREA': item.especialidad,
                 'INVOLUCRADOS': item.responsable,
                 'FECHA': fechaStr,
                 'RELOJ': item.horas,
                 'ESTATUS': "ASIGNADO",
                 'PRIORIDAD': item.prioridad || item.prioridades,
                 'RESTRICCIONES': item.restricciones,
                 'RIESGOS': item.riesgos,
                 'FECHA_RESPUESTA': item.fechaRespuesta,
                 'AVANCE': "0%",
                 'COMENTARIOS': comentarios,
                 'ARCHIVO': item.archivoUrl,
                 'CUMPLIMIENTO': item.cumplimiento,
                 'COMENTARIOS PREVIOS': item.comentariosPrevios || "",
                 'REQUISITOR': item.requisitor,
                 'CONTACTO': item.contacto,
                 'CELULAR': item.celular,
                 'FECHA_COTIZACION': item.fechaCotizacion,
                 'CLIENTE': item.cliente,
                 'TRABAJO': item.TRABAJO,
                 'DETALLES_EXTRA': detallesExtra // Nueva Columna
          };
          
          // A. Persistencia en PPC Maestro (PPCV3)
          addTaskToSheet(APP_CONFIG.ppcSheetName, taskData);

          // A.1. Persistencia Condicional en PPCV4 (Solo ANTONIA_VENTAS)
          if (String(activeUser).toUpperCase().trim() === 'ANTONIA_VENTAS') {
              // Create specific task object for PPCV4 to match headers exactly if aliases fail
              const taskPPC4 = { ...taskData };
              // Ensure critical fields map to Screenshot Headers
              if (taskData['FECHA']) taskPPC4['Fecha de Alta'] = taskData['FECHA'];
              if (taskData['CONCEPTO']) taskPPC4['Descripción de la Actividad'] = taskData['CONCEPTO'];
              if (taskData['ARCHIVO']) taskPPC4['Archivos'] = taskData['ARCHIVO'];
              if (taskData['COMENTARIOS']) taskPPC4['Comentarios Semana en Curso'] = taskData['COMENTARIOS'];
              if (taskData['INVOLUCRADOS']) taskPPC4['RESPONSABLE'] = taskData['INVOLUCRADOS'];

              addTaskToSheet('PPCV4', taskPPC4);
          }

          // B. Respaldo Obligatorio en ADMINISTRADOR (Control)
          addTaskToSheet("ADMINISTRADOR", taskData);

          // C. Distribución al Staff (Tracker Personal)
          const responsables = String(item.responsable || "").split(",").map(s => s.trim()).filter(s => s);
          responsables.forEach(personName => {
              if (!personName.toUpperCase().includes("(VENTAS)")) {
                  addTaskToSheet(personName, taskData);
              }
          });

          // D. Preparar Log (En Memoria)
          logEntries.push([new Date(), activeUser || "DESCONOCIDO", "GUARDADO_PPC", `ID: ${id} | Comentarios: ${comentarios}`]);
      });

      // 3. EJECUCIÓN DE ESCRITURA (BATCH)

      // A. Guardado Crítico (PPCV3)
      // Usamos useOwnLock = false porque ya tenemos el lock aquí.
      if (tasksBySheet[APP_CONFIG.ppcSheetName]) {
          const ppcResult = internalBatchUpdateTasks(APP_CONFIG.ppcSheetName, tasksBySheet[APP_CONFIG.ppcSheetName], false);
          if (!ppcResult.success) {
              throw new Error("CRITICAL: Falló guardado en PPCV3. " + ppcResult.message);
          }
          delete tasksBySheet[APP_CONFIG.ppcSheetName];
      }

      // B. Distribución Secundaria (Staff / Admin)
      for (const [targetSheet, tasks] of Object.entries(tasksBySheet)) {
          try {
            const res = internalBatchUpdateTasks(targetSheet, tasks, false);
            if (!res.success) console.warn(`Fallo secundario en ${targetSheet}: ${res.message}`);
          } catch(err) {
             console.warn(`Error en distribución a ${targetSheet}: ${err.toString()}`);
          }
      }

      // C. Escritura de Logs en Lote (Optimización V8)
      if (logEntries.length > 0) {
        try {
            let sheetLog = SS.getSheetByName(APP_CONFIG.logSheetName);
            if (!sheetLog) {
              sheetLog = SS.insertSheet(APP_CONFIG.logSheetName);
              sheetLog.appendRow(["FECHA", "USUARIO", "ACCION", "DETALLES"]);
            }
            const lastRow = sheetLog.getLastRow();
            // batch write logs
            sheetLog.getRange(lastRow + 1, 1, logEntries.length, 4).setValues(logEntries);
        } catch(logErr) {
            console.error("Error escribiendo logs: " + logErr.toString());
        }
      }

      return { success: true, message: "Datos procesados y distribuidos correctamente.", ids: generatedIds };
    } catch (e) { 
        console.error(e);
        registrarLog(activeUser || "SYSTEM", "ERROR_CRITICO_PPC", e.toString());
        return { success: false, message: "Error al guardar: " + e.toString() };
    } finally {
        lock.releaseLock();
    }
  }
  return { success: false, message: "Sistema Ocupado, intenta de nuevo." };
}

function uploadFileToDrive(data, type, name) {
  try {
    const folderId = APP_CONFIG.folderIdUploads;
    let folder;
    if (folderId && folderId.trim() !== "") { try { folder = DriveApp.getFolderById(folderId); } catch(e) { folder = DriveApp.getRootFolder();
    } } 
    else { folder = DriveApp.getRootFolder();
    }
    // FIX: Default to octet-stream if type is missing (e.g. .dwg, .zip)
    const mimeType = (type && type.trim() !== "") ? type : "application/octet-stream";
    const blob = Utilities.newBlob(Utilities.base64Decode(data.split(',')[1]), mimeType, name);
    const file = folder.createFile(blob);
    file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
    return { success: true, fileUrl: file.getUrl() };
  } catch (e) { return { success: false, message: e.toString() };
  }
}

function apiFetchPPCData() { 
  try { 
    const s = findSheetSmart(APP_CONFIG.ppcSheetName);
    if(!s) return {success:true,data:[]};
    const range = s.getDataRange();
    const values = range.getValues();
    if (values.length < 2) return {success:true, data:[]};
    const headerIdx = findHeaderRow(values);
    if (headerIdx === -1) return {success:true, data:[]};

    const headers = values[headerIdx].map(h => String(h).toUpperCase().replace(/\n/g, " ").trim());
    const colMap = {
      id: headers.findIndex(h => h.includes("ID") || h.includes("FOLIO")),
      esp: headers.findIndex(h => h.includes("ESPECIALIDAD")),
      con: headers.findIndex(h => h.includes("DESCRIPCI") || h.includes("CONCEPTO")), 
      resp: headers.findIndex(h => h.includes("RESPONSABLE") || h.includes("INVOLUCRADOS")),
      fecha: headers.findIndex(h => h.includes("FECHA") || h.includes("ALTA")),
      reloj: headers.findIndex(h => h.includes("RELOJ")),
      cump: headers.findIndex(h => h.includes("CUMPLIMIENTO")),
      arch: headers.findIndex(h => h.includes("ARCHIVO") || h.includes("CLIP")),
      com: headers.findIndex(h => (h.includes("COMENTARIOS") && h.includes("CURSO")) || h === "COMENTARIOS"),
      prev: headers.findIndex(h => (h.includes("COMENTARIOS") && h.includes("PREVIA")) || h.includes("PREVIOS"))
    };

    let dataRows = values.slice(headerIdx + 1);
    if(dataRows.length > 300) dataRows = dataRows.slice(dataRows.length - 300);
    const resultData = dataRows.map(r => {
      const getVal = (idx) => (idx > -1 && r[idx] !== undefined) ? r[idx] : "";
      return {
        id: getVal(colMap.id), especialidad: getVal(colMap.esp), concepto: getVal(colMap.con),
        responsable: getVal(colMap.resp), fechaAlta: getVal(colMap.fecha), horas: getVal(colMap.reloj),
        cumplimiento: getVal(colMap.cump), archivoUrl: getVal(colMap.arch), comentarios: getVal(colMap.com),
        comentariosPrevios: getVal(colMap.prev)
      };
    }).filter(x => x.concepto).reverse();
    return { success: true, data: resultData }; 
  } catch(e){ return {success:false, message: e.toString()} } 
}

function apiFetchWeeklyPlanData(username) {
  try {
    const sheetName = (String(username).toUpperCase().trim() === 'ANTONIA_VENTAS') ? 'PPCV4' : APP_CONFIG.ppcSheetName;
    const sheet = findSheetSmart(sheetName);
    if (!sheet) return { success: false, message: "No existe la hoja " + sheetName };
    const data = sheet.getDataRange().getValues();
    if (data.length < 2) return { success: true, headers: [], data: [] };
    const headerRowIdx = findHeaderRow(data);
    if (headerRowIdx === -1) return { success: false, message: "Cabeceras no encontradas en PPCV3." };
    const originalHeaders = data[headerRowIdx].map(h => String(h).trim());
    
    const mappedHeaders = originalHeaders.map(h => {
        const up = h.toUpperCase();
        if (up.includes("ESPECIALIDAD") || up.includes("AREA") || up.includes("DEPARTAMENTO")) return "ESPECIALIDAD";
        if (up.includes("DESCRIPCI") || up.includes("CONCEPTO")) return "CONCEPTO"; 
        if (up.includes("INVOLUCRADOS") || up.includes("RESPONSABLE") || up.includes("VENDEDOR") || up.includes("ENCARGADO")) return "RESPONSABLE";
        if (up.includes("ALTA") || up.includes("FECHA")) return "FECHA";
        if (up.includes("RELOJ") || up.includes("HORAS")) return "RELOJ";
        if (up.includes("ARCHIV") || up.includes("CLIP") || up.includes("LINK") || up.includes("EVIDENCIA")) return "ARCHIVO";
        if (up.includes("CUMPLIMIENTO")) return "CUMPLIMIENTO";
        if (up === "COMENTARIOS" || up === "COMENTARIOS SEMANA EN CURSO" || up.includes("OBSERVACIONES")) return "COMENTARIOS SEMANA EN CURSO";
        if (up === "COMENTARIOS PREVIOS" || up === "COMENTARIOS SEMANA PREVIA" || up === "PREVIOS") return "COMENTARIOS SEMANA PREVIA";
        return up; 
    });
    const displayHeaders = ["SEMANA", ...mappedHeaders];
    const rows = data.slice(headerRowIdx + 1);
    const result = rows.map((r, i) => {
      const rowObj = { _rowIndex: headerRowIdx + i + 2 };
      mappedHeaders.forEach((h, colIdx) => {
        let val = r[colIdx];
        if (val instanceof Date) {
           if (val.getFullYear() < 1900) {
              val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "HH:mm");
           } else {
              val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
           }
        }
        rowObj[h] = val;
      });
      const fechaVal = rowObj["FECHA"];
      let semanaNum = "-";
      if (fechaVal) {
        let dateObj = null;
        if (String(fechaVal).includes("/")) {
          const parts = String(fechaVal).split("/"); 
          if(parts.length === 3) dateObj = new Date(parts[2], parts[1]-1, parts[0]);
        } else if (fechaVal instanceof Date) { dateObj = fechaVal; } else { dateObj = new Date(fechaVal); }
        if (dateObj && !isNaN(dateObj.getTime())) semanaNum = getWeekNumber(dateObj); 
      }
      rowObj["SEMANA"] = semanaNum;
      
      return rowObj;
    }).filter(r => r["CONCEPTO"] || r["ID"] || r["FOLIO"]);
    return { success: true, headers: displayHeaders, data: result.reverse() }; 
  } catch (e) {
    console.error(e);
    return { success: false, message: e.toString() };
  }
}

function getWeekNumber(d) {
  d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay()||7));
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(),0,1));
  var weekNo = Math.ceil(( ( (d - yearStart) / 86400000) + 1)/7);
  return weekNo;
}

// 1. Guardar Nuevo Sitio (Padre)
function apiSaveSite(siteData) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(5000)) {
    try {
      let sheet = findSheetSmart("DB_SITIOS");
      if (!sheet) {
        sheet = SS.insertSheet("DB_SITIOS");
        sheet.appendRow(["ID_SITIO", "NOMBRE", "CLIENTE", "TIPO", "ESTATUS", "FECHA_CREACION", "CREADO_POR"]);
      }
      
      const data = sheet.getDataRange().getValues();
      const cleanName = siteData.name.toUpperCase().trim();
      const nameColIdx = data.length > 0 ? data[0].indexOf("NOMBRE") : 1;
      for(let i=1; i<data.length; i++) {
         if (data[i][nameColIdx] && String(data[i][nameColIdx]).toUpperCase().trim() === cleanName) {
             return { success: false, message: "Ya existe un sitio con ese nombre."};
         }
      }

      const id = "SITE-" + new Date().getTime();
      sheet.appendRow([
        id,
        cleanName,
        siteData.client.toUpperCase().trim(),
        siteData.type || "CLIENTE", 
        "ACTIVO",
        new Date(),
        siteData.createdBy ? siteData.createdBy.toUpperCase().trim() : "ANONIMO"
      ]);
      SpreadsheetApp.flush(); 

      // AUTOMATIZACIÓN: CREAR ESTRUCTURA ESTÁNDAR AUTOMÁTICAMENTE
      apiCreateStandardStructure(id, siteData.createdBy);

      registrarLog(siteData.createdBy || "ANONIMO", "NUEVO SITIO", `Sitio: ${cleanName} (${id})`);

      return { success: true, id: id, message: "Sitio creado correctamente con estructura PPC completa." };
    } catch (e) {
      return { success: false, message: e.toString() };
    } finally {
      lock.releaseLock();
    }
  }
  return { success: false, message: "El sistema está ocupado." };
}

// 2. Guardar Nuevo Subproyecto (Hijo)
function apiSaveSubProject(subProjectData) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(5000)) {
    try {
      let sheet = findSheetSmart("DB_PROYECTOS");
      if (!sheet) {
        sheet = SS.insertSheet("DB_PROYECTOS");
        sheet.appendRow(["ID_PROYECTO", "ID_SITIO", "NOMBRE_SUBPROYECTO", "TIPO", "ESTATUS", "FECHA_CREACION", "CREADO_POR"]);
      }
      
      const cleanName = subProjectData.name.toUpperCase().trim();
      const data = sheet.getDataRange().getValues();
      let idSitioIdx = 1; 
      let nameIdx = 2;
      const headerRow = findHeaderRow(data);
      if (headerRow > -1) {
          const headers = data[headerRow].map(h=>String(h).toUpperCase());
          idSitioIdx = headers.indexOf("ID_SITIO");
          nameIdx = headers.indexOf("NOMBRE_SUBPROYECTO");
      }

      for(let i=1; i<data.length; i++) {
          if (data[i][idSitioIdx] == subProjectData.parentId && 
              String(data[i][nameIdx]).toUpperCase().trim() === cleanName) {
              return { success: false, message: "Ya existe ese subproyecto en este sitio."};
          }
      }

      const id = "PROJ-" + new Date().getTime() + "-" + Math.floor(Math.random()*1000);
      sheet.appendRow([
        id,
        subProjectData.parentId,
        cleanName,
        subProjectData.type || "GENERAL", 
        "ACTIVO",
        new Date(),
        subProjectData.createdBy ? subProjectData.createdBy.toUpperCase().trim() : "ANONIMO"
      ]);
      SpreadsheetApp.flush(); 

      registrarLog(subProjectData.createdBy || "ANONIMO", "NUEVO SUBPROYECTO", `Subproyecto: ${cleanName} (${id})`);

      return { success: true, id: id, message: "Subproyecto agregado." };
    } catch (e) {
      return { success: false, message: e.toString() };
    } finally {
      lock.releaseLock();
    }
  }
  return { success: false, message: "El sistema está ocupado." };
}

// 3. Obtener Árbol Completo
function apiFetchCascadeTree() {
  try {
    const sites = [];
    const sheetSites = findSheetSmart("DB_SITIOS");
    if (sheetSites) {
      const values = sheetSites.getDataRange().getValues();
      const headerRowIdx = findHeaderRow(values);
      if (headerRowIdx !== -1 && values.length > headerRowIdx + 1) {
        const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
        const colMap = {
           id: headers.findIndex(h => h.includes("ID")),
           name: headers.findIndex(h => h.includes("NOMBRE")),
           client: headers.findIndex(h => h.includes("CLIENTE")),
           type: headers.findIndex(h => h.includes("TIPO")),
           status: headers.findIndex(h => h.includes("ESTATUS")),
           date: headers.findIndex(h => h.includes("FECHA"))
        };
        for (let i = headerRowIdx + 1; i < values.length; i++) {
          const row = values[i];
          if (colMap.id > -1 && colMap.name > -1 && row[colMap.id]) {
             let dateStr = "";
             if (colMap.date > -1 && row[colMap.date]) {
                 try { dateStr = Utilities.formatDate(new Date(row[colMap.date]), SS.getSpreadsheetTimeZone(), "dd/MM/yy HH:mm");
                 } catch(e) {}
             }
             sites.push({
               id: String(row[colMap.id]).trim(),
               name: String(row[colMap.name]).trim(),
               client: (colMap.client > -1) ? String(row[colMap.client]) : "",
               type: (colMap.type > -1) ? String(row[colMap.type]) : "CLIENTE",
               status: (colMap.status > -1) ? String(row[colMap.status]) : "ACTIVO",
               createdAt: dateStr,
               subProjects: [],
               expanded: false
             });
          }
        }
      }
    }

    const sheetProjs = findSheetSmart("DB_PROYECTOS");
    if (sheetProjs) {
      const values = sheetProjs.getDataRange().getValues();
      const headerRowIdx = findHeaderRow(values);
      if (headerRowIdx !== -1 && values.length > headerRowIdx + 1) {
        const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
        const colMap = {
           parentId: headers.findIndex(h => h.includes("SITIO") || h.includes("PADRE")),
           name: headers.findIndex(h => h.includes("NOMBRE") || h.includes("SUBPROYECTO")),
           type: headers.findIndex(h => h.includes("TIPO") || h.includes("ESPECIALIDAD")),
           status: headers.findIndex(h => h.includes("ESTATUS"))
        };
        for (let i = headerRowIdx + 1; i < values.length; i++) {
          const row = values[i];
          if (colMap.parentId > -1 && colMap.name > -1 && row[colMap.parentId]) {
             const parentId = String(row[colMap.parentId]).trim();
             const parent = sites.find(s => String(s.id).trim() === parentId);
             if (parent) {
               // CAMBIO: Si es PPC, asignamos el icono correcto
               const pName = String(row[colMap.name]).trim().toUpperCase();
               let icon = "fa-clipboard-list";
               if (pName.includes("PPC")) icon = "fa-tasks";

               parent.subProjects.push({
                 id: row[0],
                 name: String(row[colMap.name]).trim(),
                 type: (colMap.type > -1) ? String(row[colMap.type]) : "GENERAL",
                 status: (colMap.status > -1) ? String(row[colMap.status]) : "ACTIVO",
                 icon: icon
               });
             }
          }
        }
      }
    }
    return { success: true, data: sites };
  } catch (e) {
    console.error(e);
    return { success: false, message: "Error leyendo DB: " + e.toString() };
  }
}

function apiFetchProjectTasks(projectName) {
  try {
    const sheet = findSheetSmart("ADMINISTRADOR");
    if (!sheet) return { success: false, message: "No se encuentra la hoja ADMINISTRADOR" };

    const values = sheet.getDataRange().getValues();
    if (values.length < 2) return { success: true, data: [], headers: [] };

    const headerRowIdx = findHeaderRow(values);
    if (headerRowIdx === -1) return { success: false, message: "Sin cabeceras válidas" };

    const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
    const projectTag = `[PROY: ${String(projectName).toUpperCase().trim()}]`;
    
    // Indices clave
    let colIdx = {
       concepto: headers.indexOf("CONCEPTO"),
       comentarios: headers.indexOf("COMENTARIOS")
    };
    if (colIdx.concepto === -1) colIdx.concepto = headers.findIndex(h => h.includes("CONCEPTO") || h.includes("DESCRIPCI"));
    if (colIdx.comentarios === -1) colIdx.comentarios = headers.findIndex(h => h.includes("COMENTARIOS"));
    const dataRows = values.slice(headerRowIdx + 1);
    const filteredTasks = [];
    for (let i = 0; i < dataRows.length; i++) {
        const row = dataRows[i];
        const comText = (colIdx.comentarios > -1 && row[colIdx.comentarios]) ? String(row[colIdx.comentarios]).toUpperCase() : "";
        const descText = (colIdx.concepto > -1 && row[colIdx.concepto]) ? String(row[colIdx.concepto]).toUpperCase() : "";
        if (comText.includes(projectTag) || descText.includes(projectTag)) {
            let rowObj = { _rowIndex: headerRowIdx + i + 2 };
            headers.forEach((h, k) => {
                let val = row[k];
                if (val instanceof Date) {
                    val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
                }
                rowObj[h] = val;
            });
            filteredTasks.push(rowObj);
        }
    }
    return { success: true, data: filteredTasks.reverse(), headers: headers };
  } catch (e) {
    console.error(e);
    return { success: false, message: e.toString() };
  }
}

// *** MODIFICADO PARA INCLUIR ETIQUETAS DE LOS NUEVOS PPCs ***
function apiSaveProjectTask(taskData, projectName, username) {
    try {
        const nameUpper = String(projectName).toUpperCase().trim();
        const tag = `[PROY: ${nameUpper}]`;
        
        let coms = taskData['COMENTARIOS'] || "";
        
        // Verificamos si ya tiene la etiqueta para no duplicar
        if (!String(coms).toUpperCase().includes(tag)) {
            taskData['COMENTARIOS'] = (coms + " " + tag).trim();
        }
        
        const res = internalBatchUpdateTasks("ADMINISTRADOR", [taskData]);
        if(res.success) {
            registrarLog(username || "DESCONOCIDO", "ACTUALIZAR PROYECTO", `Proyecto: ${projectName}, ID: ${taskData['ID']||taskData['FOLIO']}`);
        }
        return res;
    } catch (e) {
        return { success: false, message: e.toString() };
    }
}

/**
 * ======================================================================
 * FUNCIONALIDAD ADICIONAL: BOTONES EN HOJA (COMANDOS UI)
 * ======================================================================
 */

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  ui.createMenu('⚡ HOLTMONT CMD')
    .addItem('✅ REALIZAR ALTA (Fila Actual)', 'cmdRealizarAlta')
    .addItem('🔄 ACTUALIZAR (Fila Actual)', 'cmdActualizar')
    .addSeparator()
    .addItem('🎨 Aplicar Formato Condicional (Semaforo)', 'setupConditionalFormatting')
    .addToUi();
}

/**
 * ASIGNAR A BOTÓN: "REALIZAR ALTA"
 * Lee la fila activa, genera ID si falta, y distribuye.
 */
function cmdRealizarAlta() {
  const sheet = SS.getActiveSheet();
  const row = sheet.getActiveRange().getRow();
  const ui = SpreadsheetApp.getUi();
  
  const dataRange = sheet.getDataRange();
  const values = dataRange.getValues();
  const headerIdx = findHeaderRow(values);

  if (headerIdx === -1 || row <= headerIdx + 1) {
    ui.alert("⚠️ Por favor selecciona una celda dentro de una fila de datos válida.");
    return;
  }

  const headers = values[headerIdx].map(h => String(h).toUpperCase().trim());
  const rowData = values[row - 1];
  const taskObj = {};
  headers.forEach((h, i) => {
    if (h) taskObj[h] = rowData[i];
  });
  if (!taskObj["CONCEPTO"] && !taskObj["DESCRIPCION"]) {
    ui.alert("❌ Falta el CONCEPTO o DESCRIPCIÓN.");
    return;
  }

  if (!taskObj["FOLIO"] && !taskObj["ID"]) {
    taskObj["FOLIO"] = "PPC-" + Math.floor(Math.random() * 100000);
    const folioCol = headers.indexOf("FOLIO") > -1 ? headers.indexOf("FOLIO") : headers.indexOf("ID");
    if (folioCol > -1) {
      sheet.getRange(row, folioCol + 1).setValue(taskObj["FOLIO"]);
    }
  }

  SS.toast("Guardando y distribuyendo tarea...", "Holtmont", 5);
  
  const currentSheetName = sheet.getName();
  taskObj['ESTATUS'] = taskObj['ESTATUS'] || 'ASIGNADO';
  const involucrados = taskObj["INVOLUCRADOS"] || taskObj["RESPONSABLE"] || "";
  const listaInv = String(involucrados).split(",").map(s => s.trim()).filter(s => s);
  
  internalBatchUpdateTasks("ADMINISTRADOR", [taskObj]);
  listaInv.forEach(nombre => {
    internalBatchUpdateTasks(nombre, [taskObj]);
  });
  if (currentSheetName !== "ADMINISTRADOR" && !listaInv.includes(currentSheetName)) {
    internalBatchUpdateTasks(currentSheetName, [taskObj]);
  }

  ui.alert(`✅ Tarea Guardada: ${taskObj["FOLIO"] || taskObj["ID"]}\nDistribulda a: ADMINISTRADOR y ${listaInv.join(", ")}`);
}

/**
 * ASIGNAR A BOTÓN: "ACTUALIZAR"
 */
function cmdActualizar() {
  const sheet = SS.getActiveSheet();
  const row = sheet.getActiveRange().getRow();
  const ui = SpreadsheetApp.getUi();

  const dataRange = sheet.getDataRange();
  const values = dataRange.getValues();
  const headerIdx = findHeaderRow(values);
  if (headerIdx === -1 || row <= headerIdx + 1) {
    ui.alert("⚠️ Selecciona una fila de datos válida.");
    return;
  }

  const headers = values[headerIdx].map(h => String(h).toUpperCase().trim());
  const rowData = values[row - 1];
  const taskObj = { _rowIndex: row }; 

  headers.forEach((h, i) => {
    if (h) taskObj[h] = rowData[i];
  });
  const id = taskObj["FOLIO"] || taskObj["ID"];
  if (!id) {
    ui.alert("❌ No se encontró un FOLIO o ID en esta fila. No se puede sincronizar.");
    return;
  }

  SS.toast("Sincronizando cambios...", "Holtmont", 3);

  const resLocal = internalBatchUpdateTasks(sheet.getName(), [taskObj]);
  if (sheet.getName() !== "ADMINISTRADOR") {
     const syncObj = { ...taskObj };
     delete syncObj._rowIndex;
     internalBatchUpdateTasks("ADMINISTRADOR", [syncObj]);
  }

  if (resLocal.moved) {
    ui.alert("✅ Tarea Actualizada y ARCHIVADA (Completada).");
  } else {
    SS.toast("✅ Actualización completada.");
  }
}

// --- FUNCIÓN GENERADORA (NUEVA) ---
// Usar esta función para crear los subproyectos automáticamente
function apiCreateStandardStructure(siteId, user) {
    STANDARD_PROJECT_STRUCTURE.forEach(name => {
        // Determinamos el tipo para que el Front sepa cómo dibujarlo
        let tipo = "GENERAL";
        if (name.includes("PPC")) tipo = "PPC_MASTER"; 
        
        apiSaveSubProject({
            parentId: siteId,
            name: name,
            type: tipo,
            createdBy: user || "SISTEMA"
        });
    });
}

/**
 * GENERADOR DE FOLIO NUMÉRICO SECUENCIAL (NUEVO)
 */
function generateNumericSequence(key) {
  const lock = LockService.getScriptLock();
  try {
    if (lock.tryLock(5000)) {
       const props = PropertiesService.getScriptProperties();
       let val = Number(props.getProperty(key) || 1000);
       val++;
       props.setProperty(key, String(val));
       return String(val);
    }
  } catch(e) { console.error(e); } finally { lock.releaseLock(); }
  return String(new Date().getTime());
}

/**
 * GENERADOR DE UNIQUEID (APP-SHEET STYLE)
 * Genera string alfanumérico de 8 caracteres.
 * (MANTENIDO POR COMPATIBILIDAD, AUNQUE DEPRECADO EN FLUJOS NUEVOS)
 */
function generateAppSheetId() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  for (let i = 0; i < 8; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

function generateWorkOrderFolio(clientName, deptName) {
  try {
      const props = PropertiesService.getScriptProperties();
      // Incrementar secuencia
      let seq = Number(props.getProperty('WORKORDER_SEQ') || 0) + 1;
      props.setProperty('WORKORDER_SEQ', String(seq));

      const seqStr = String(seq).padStart(4, '0');

      // Abreviatura Cliente: Iniciales de las primeras 2 palabras o primeras 2 letras
      const cleanClient = (clientName || "XX").toUpperCase().replace(/[^A-Z0-9]/g, ' ').trim();
      const words = cleanClient.split(/\s+/).filter(w => w.length > 0);
      let clientStr = "XX";
      if (words.length >= 2) {
          clientStr = words[0][0] + words[1][0];
      } else if (words.length === 1) {
          clientStr = words[0].substring(0, 2);
      }

      // Simplificar departamento
      const rawDept = (deptName || "General").trim().toUpperCase();
      const ABBR_MAP = {
          "ELECTROMECANICA": "Electro",
          "ELECTROMECÁNICA": "Electro",
          "CONSTRUCCION": "Const",
          "CONSTRUCCIÓN": "Const",
          "MANTENIMIENTO": "Mtto",
          "REMODELACION": "Remod",
          "REMODELACIÓN": "Remod",
          "REPARACION": "Repar",
          "REPARACIÓN": "Repar",
          "RECONFIGURACION": "Reconf",
          "RECONFIGURACIÓN": "Reconf",
          "POLIZA": "Poliza",
          "PÓLIZA": "Poliza",
          "INSPECCION": "Insp",
          "INSPECCIÓN": "Insp",
          "ADMINISTRACION": "Admin",
          "ADMINISTRACIÓN": "Admin",
          "MAQUINARIA": "Maq",
          "DISEÑO": "Diseño",
          "COMPRAS": "Compras",
          "VENTAS": "Ventas",
          "HVAC": "HVAC",
          "SEGURIDAD": "EHS",
          "EHS": "EHS"
      };

      let deptStr = ABBR_MAP[rawDept];

      // Si no está en el mapa, intentar capitalizar primera letra y resto minúsculas
      if (!deptStr) {
          if (rawDept.length > 6) {
              deptStr = rawDept.substring(0, 1) + rawDept.substring(1, 5).toLowerCase();
          } else {
              deptStr = rawDept.substring(0, 1) + rawDept.substring(1).toLowerCase();
          }
      }

      const date = new Date();
      const d = String(date.getDate()).padStart(2, '0');
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const y = String(date.getFullYear()).slice(-2);
      const dateStr = `${d}${m}${y}`;

      return `${seqStr}${clientStr} ${deptStr} ${dateStr}`;
  } catch(e) {
      console.error(e);
      return "WO-" + new Date().getTime();
  }
}

function apiGetNextWorkOrderSeq() {
  try {
    const props = PropertiesService.getScriptProperties();
    let seq = Number(props.getProperty('WORKORDER_SEQ') || 0) + 1;
    return String(seq).padStart(4, '0');
  } catch(e) {
    return "0000";
  }
}

/*
 * ======================================================================
 * AUTOMATIZACIÓN DIARIA: CONTADOR DE DÍAS (VENTAS)
 * ======================================================================
 */
function incrementarContadorDias() {
  // Lista de hojas a procesar (Antonia + Vendedores)
  const sheetsToProcess = ["ANTONIA_VENTAS"];
  
  try {
      const directory = getDirectoryFromDB();
      directory.forEach(user => {
          if ((user.dept === 'VENTAS' || user.type === 'VENTAS' || user.type === 'HIBRIDO') && user.name !== "ANTONIA_VENTAS") {
              sheetsToProcess.push(user.name + " (VENTAS)"); // Estándar: NOMBRE (VENTAS)
              // También intentar sin sufijo si es un usuario que usa su hoja principal como ventas (poco probable en config actual pero por seguridad)
              if (user.type === 'VENTAS') sheetsToProcess.push(user.name);
          }
      });
  } catch(e) { console.error("Error obteniendo directorio para contador", e); }

  // Eliminar duplicados
  const uniqueSheets = [...new Set(sheetsToProcess)];

  const today = new Date();
  today.setHours(0,0,0,0);

  uniqueSheets.forEach(sheetName => {
      try {
        const sheet = findSheetSmart(sheetName);
        if (!sheet) return;

        const dataRange = sheet.getDataRange();
        const values = dataRange.getValues();
        if (values.length < 2) return; 

        // Buscar Cabeceras
        const headerRowIdx = findHeaderRow(values);
        if (headerRowIdx === -1) return;

        const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
        
        // Buscar columnas clave
        let diasIdx = headers.findIndex(h => h === "DIAS" || h === "RELOJ");
        
        const fechaAliases = ['FECHA', 'FECHA ALTA', 'FECHA INICIO', 'ALTA', 'FECHA DE INICIO'];
        let fechaIdx = -1;
        for(let alias of fechaAliases) {
            const idx = headers.indexOf(alias);
            if(idx > -1) { fechaIdx = idx; break; }
        }

        if (diasIdx === -1 || fechaIdx === -1) return;

        const newColumnValues = [];
        let updatedCount = 0;
        let startRow = headerRowIdx + 1; // 0-based index of first data row

        // Iterar solo datos
        for (let i = startRow; i < values.length; i++) {
            let fechaVal = values[i][fechaIdx];
            let newVal = values[i][diasIdx];

            // Lógica: TODAY - FECHA = DÍAS
            let calculated = false;
            if (fechaVal instanceof Date) {
                fechaVal.setHours(0,0,0,0);
                const diffTime = today - fechaVal;
                const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
                newVal = Math.max(0, diffDays);
                calculated = true;
            } else if (typeof fechaVal === 'string' && fechaVal.trim() !== "") {
                if(fechaVal.match(/\d{1,2}\/\d{1,2}\/\d{2,4}/)) {
                    try {
                        const parts = fechaVal.split('/');
                        let y = parts[2];
                        if(y.length === 2) y = '20'+y;
                        const dObj = new Date(y, parts[1]-1, parts[0]);
                        if(!isNaN(dObj.getTime())) {
                            dObj.setHours(0,0,0,0);
                            const diffDays = Math.floor((today - dObj) / (1000 * 60 * 60 * 24));
                            newVal = Math.max(0, diffDays);
                            calculated = true;
                        }
                    } catch(e) {}
                }
            }
            
            if (calculated) updatedCount++;
            else if (newVal === undefined) newVal = ""; // Keep clean if calculation fails
            
            newColumnValues.push([newVal]);
        }

        // Batch Update
        if (newColumnValues.length > 0) {
            sheet.getRange(startRow + 1, diasIdx + 1, newColumnValues.length, 1).setValues(newColumnValues);
            // Re-apply traffic light just in case
            try { applyTrafficLightToSheet(sheet); } catch(e){}
        }
        
        console.log(`[CONTADOR] ${sheetName}: ${updatedCount} actualizados.`);

      } catch (e) {
        console.error(`Error procesando ${sheetName}:`, e);
      }
  });
  
  registrarLog("SISTEMA", "CONTADOR_DIARIO", `Actualización masiva de días completada.`);
}

function instalarDisparador() {
  const funcionObjetivo = "incrementarContadorDias";

  // Verificar si ya existe el disparador para evitar duplicados
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === funcionObjetivo) {
      console.log(`El disparador para '${funcionObjetivo}' ya existe.`);
      return;
    }
  }

  // Crear nuevo disparador diario entre 1 am y 2 am
  ScriptApp.newTrigger(funcionObjetivo)
      .timeBased()
      .everyDays(1)
      .atHour(1) // 1 am
      .create();

  console.log(`Disparador instalado para '${funcionObjetivo}' (Diario 1am-2am).`);
  registrarLog("ADMIN", "CONFIG_TRIGGER", "Se instaló el disparador automático diario.");
}

function generarFolioAutomatico(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
  } catch (e) {
    console.error('Could not obtain lock after 30 seconds.');
    return;
  }

  try {
    const ss = e ? e.source : SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(FOLIO_CONFIG.SHEET_NAME);

    if (!sheet) return;

    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return;

    const lastCol = sheet.getLastColumn();
    const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    const folioIndex = headers.indexOf(FOLIO_CONFIG.COLUMN_NAME);

    if (folioIndex === -1) {
      console.error(`Column '${FOLIO_CONFIG.COLUMN_NAME}' not found in sheet '${FOLIO_CONFIG.SHEET_NAME}'`);
      return;
    }

    const folioColNum = folioIndex + 1;
    const targetCell = sheet.getRange(lastRow, folioColNum);
    const targetValue = targetCell.getValue();

    if (targetValue === "" || targetValue === null) {
      let newFolio = 1;

      if (lastRow > 2) {
        const numRows = lastRow - 2;
        if (numRows > 0) {
            const previousValues = sheet.getRange(2, folioColNum, numRows, 1).getValues().flat();
            const numbers = previousValues.filter(val => typeof val === 'number' && !isNaN(val));
            if (numbers.length > 0) {
              const maxVal = Math.max(...numbers);
              newFolio = maxVal + 1;
            }
        }
      }

      targetCell.setValue(newFolio);
      console.log(`Generated Folio: ${newFolio} for row ${lastRow}`);
    }

  } catch (err) {
    console.error(err);
  } finally {
    lock.releaseLock();
  }
}

// ==========================================
// _TEST_SUITE.js
// ==========================================

function test_SavePPCV3_Flow() {
  console.log("🛠️ INICIANDO TEST: Persistencia en PPCV3");

  // 1. Simular Payload
  const testId = "TEST-" + new Date().getTime();
  const payload = {
    concepto: "TEST_AUTO_UNITARIO_" + testId,
    especialidad: "PRUEBAS",
    responsable: "JESUS_CANTU",
    horas: "1",
    prioridad: "Alta",
    comentarios: "Prueba de integridad de datos",
    // Explicit ID for verification
    id: testId
  };

  const user = "JESUS_CANTU";

  console.log("📋 Payload simulado:", payload);

  // 2. Ejecutar Guardado
  const result = apiSavePPCData(payload, user);

  if (!result.success) {
    console.error("❌ FALLO: La función apiSavePPCData retornó error.", result);
    return;
  }
  console.log("✅ apiSavePPCData ejecutado con éxito.");

  // 3. Verificación
  const sheet = SS.getSheetByName(APP_CONFIG.ppcSheetName);
  const data = sheet.getDataRange().getValues();

  // Buscar el ID
  let found = false;
  let foundRowData = [];

  // Asumimos que los headers están en alguna fila, usamos findHeaderRow o búsqueda bruta
  // Búsqueda bruta del ID en toda la hoja para estar seguros
  for (let i = 0; i < data.length; i++) {
    const rowStr = data[i].join("|");
    if (rowStr.includes(testId)) {
      found = true;
      foundRowData = data[i];
      break;
    }
  }

  if (found) {
    console.log("✅ PRUEBA PASADA: Datos persistidos en PPCV3. ID encontrado: " + testId);
    console.log("📄 Datos de fila:", foundRowData);
  } else {
    console.error("❌ FALLO: Datos no encontrados en PPCV3. El ID " + testId + " no aparece en la hoja.");
    // Log last 5 rows for debug
    console.log("🔍 Últimas 5 filas de la hoja:", data.slice(-5));
    throw new Error("Persistencia fallida en PPCV3");
  }
}

function test_WorkOrder_Generation() {
  console.log("🛠️ INICIANDO TEST: Workorder ID Generation");
  const user = "PREWORK_ORDER";
  const payload = {
      cliente: "MERCEDES BENZ",
      especialidad: "ELECTROMECANICA",
      concepto: "TEST WO",
      responsable: "JUAN PEREZ",
      // ...
  };

  // Call API
  const res = apiSavePPCData(payload, user);

  if (res.success && res.ids && res.ids.length > 0) {
      const id = res.ids[0];
      console.log("Generated ID:", id);
      // Expected: Sequence(4) + ME + Space + ELECTROMECANICA + Space + Date(6)
      // e.g. 0002ME ELECTROMECANICA 010126
      if (id.match(/^\d{4}[A-Z]{2} .+ \d{6}$/)) {
          console.log("✅ ID Format Correct");
      } else {
          console.error("❌ ID Format Incorrect:", id);
      }
  } else {
      console.error("❌ Failed to save or generate ID", res);
  }
}

function test_Directory_CRUD() {
  console.log("🛠️ INICIANDO TEST: Directory CRUD & Migration");

  // 1. Test Migration / Fetch
  const dir1 = getDirectoryFromDB();
  console.log("Directory Size:", dir1.length);
  if (dir1.length > 0) {
      console.log("✅ getDirectoryFromDB returned data (Migration or Fetch worked)");
  } else {
      console.error("❌ getDirectoryFromDB returned empty");
  }

  // 2. Test Add
  const testUser = { name: "TEST_USER_AUTO", dept: "TEST_DEPT", type: "ESTANDAR" };
  const addRes = apiAddEmployee(testUser);
  if (addRes.success) {
      console.log("✅ apiAddEmployee Success");
  } else {
      console.error("❌ apiAddEmployee Failed:", addRes.message);
  }

  // 3. Verify Added
  const dir2 = getDirectoryFromDB();
  const found = dir2.find(u => u.name === "TEST_USER_AUTO");
  if (found) {
      console.log("✅ User found in Directory DB");
  } else {
      console.error("❌ User NOT found in Directory DB after adding");
  }

  // 4. Test Delete
  const delRes = apiDeleteEmployee("TEST_USER_AUTO");
  if (delRes.success) {
      console.log("✅ apiDeleteEmployee Success");
  } else {
      console.error("❌ apiDeleteEmployee Failed:", delRes.message);
  }

  // 5. Verify Deleted
  const dir3 = getDirectoryFromDB();
  const found2 = dir3.find(u => u.name === "TEST_USER_AUTO");
  if (!found2) {
      console.log("✅ User successfully removed from DB");
  } else {
      console.error("❌ User STILL found in DB after deleting");
  }
}

function test_ReverseSync_Flow() {
  console.log("🛠️ INICIANDO TEST: Sincronización Inversa (Ventas -> Antonia)");

  // 1. Simular Datos de Tarea
  const testId = "TEST-SYNC-" + new Date().getTime();
  const taskData = {
    FOLIO: testId,
    CONCEPTO: "TEST_REVERSE_SYNC",
    VENDEDOR: "TEST_USER (VENTAS)",
    AVANCE: "50%",
    COTIZACION: "http://fake-url.com/cotizacion.pdf"
  };

  const personName = "TEST_USER (VENTAS)";

  // 2. Ejecutar internalUpdateTask
  // Nota: Esto intentará escribir en las hojas reales si existen.
  // En este entorno simulado, verificamos que no lance errores y que la lógica pase.

  console.log("Simulando actualización en: " + personName);
  const result = internalUpdateTask(personName, taskData, "TEST_ADMIN");

  if (result.success) {
      console.log("✅ Update local exitoso.");
      // Aquí idealmente verificaríamos que ANTONIA_VENTAS se actualizó,
      // pero sin acceso a la hoja en tiempo real, confiamos en que el log no muestre error de sync.
      console.log("ℹ️ Verificar logs del sistema para confirmar 'Sincronización Inversa'.");
  } else {
      console.error("❌ Falló update local: " + result.message);
  }
}

/**
 * ======================================================================
 * MODULE: FORMATO CONDICIONAL (SEMAFORIZACIÓN)
 * ======================================================================
 */
function applyTrafficLightToSheet(sheet) {
  if (!sheet) return false;
  const sNameUpper = sheet.getName().toUpperCase().trim();

  // Exclusiones Internas (Seguridad)
  const excludedSubstrings = ["LOG_", "DB_", "DATOS", "BORRADOR"];
  if (excludedSubstrings.some(ex => sNameUpper.includes(ex))) return false;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) return false;

  // 1. Encontrar Cabeceras
  const values = sheet.getRange(1, 1, Math.min(20, lastRow), lastCol).getValues();
  const headerRowIdx = findHeaderRow(values);
  if (headerRowIdx === -1) return false;

  const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());

  // 2. Identificar Columnas
  const fechaAliases = ['FECHA', 'FECHA ALTA', 'FECHA INICIO', 'ALTA', 'FECHA DE INICIO', 'FECHA VISITA', 'FECHA DE ALTA', 'FECHA_ALTA'];
  const colFechaIndices = [];
  headers.forEach((h, i) => {
      if (fechaAliases.includes(h) || h.startsWith("FECHA ")) {
          colFechaIndices.push(i);
      }
  });
  
  const colClasiIdx = headers.findIndex(h => h.includes("CLASIFICACION") || h.includes("CLASI"));
  const colDiasIdx = headers.findIndex(h => h === "DIAS" || h === "RELOJ");

  if (colFechaIndices.length === 0 || colClasiIdx === -1) return false;

  const rowHeader = headerRowIdx + 1; // 1-based (Fila de Titulos)
  const colClasiLet = colIndexToLetter(colClasiIdx + 1);
  
  // Identify PRIMARY Date Column (for linking DIAS coloring)
  let primaryFechaIdx = -1;
  for(let alias of fechaAliases) {
      const idx = headers.indexOf(alias);
      if(idx > -1) { primaryFechaIdx = idx; break; }
  }
  if(primaryFechaIdx === -1 && colFechaIndices.length > 0) primaryFechaIdx = colFechaIndices[0];

  // 3. Limpieza Inteligente de Reglas Antiguas
  const rules = sheet.getConditionalFormatRules();
  const cleanRules = rules.filter(r => {
      const formula = (r.getBooleanCondition() && r.getBooleanCondition().getCriteriaType() === SpreadsheetApp.BooleanCriteria.CUSTOM_FORMULA)
                      ? r.getBooleanCondition().getCriteriaValues()[0]
                      : "";
      // Eliminamos reglas de semáforo viejas (detectadas por referencia a CLASI + TODAY)
      if (formula.includes("TODAY") && formula.includes(colClasiLet) && formula.includes("ISNUMBER")) return false;
      return true;
  });

  const newRules = [];

  // 4. Iterar sobre TODAS las columnas de fecha encontradas
  colFechaIndices.forEach(idx => {
      const colFechaLet = colIndexToLetter(idx + 1);
      
      const rangesToColor = [sheet.getRange(rowHeader, idx + 1, sheet.getMaxRows() - rowHeader + 1, 1)];
      if (idx === primaryFechaIdx && colDiasIdx > -1) {
          rangesToColor.push(sheet.getRange(rowHeader, colDiasIdx + 1, sheet.getMaxRows() - rowHeader + 1, 1));
      }

      const addRulePair = (clase, dias, buffer) => {
          const formulaBase = `AND(UPPER(TRIM($${colClasiLet}${rowHeader}))="${clase}", ISNUMBER($${colFechaLet}${rowHeader}), ROW()>${rowHeader})`;
          const diffFormula = `(TODAY() - INT($${colFechaLet}${rowHeader}))`;

          // VENCIDO (ROJO): > dias
          newRules.push(SpreadsheetApp.newConditionalFormatRule()
              .whenFormulaSatisfied(`=AND(${formulaBase}, ${diffFormula} > ${dias})`)
              .setBackground("#FF0000")
              .setFontColor("#FFFFFF")
              .setRanges(rangesToColor)
              .build());

          // POR VENCER (AMARILLO): Entre (dias - buffer) y dias
          const warningStart = dias - buffer;
          newRules.push(SpreadsheetApp.newConditionalFormatRule()
              .whenFormulaSatisfied(`=AND(${formulaBase}, ${diffFormula} >= ${warningStart}, ${diffFormula} <= ${dias})`)
              .setBackground("#FFFF00")
              .setFontColor("#000000")
              .setRanges(rangesToColor)
              .build());

          // A TIEMPO (VERDE): < warningStart
          newRules.push(SpreadsheetApp.newConditionalFormatRule()
              .whenFormulaSatisfied(`=AND(${formulaBase}, ${diffFormula} < ${warningStart})`)
              .setBackground("#00FF00")
              .setFontColor("#000000")
              .setRanges(rangesToColor)
              .build());
      };

      // Configuración: Clase, Límite, Buffer (Días de aviso antes del límite)
      // Los límites deben coincidir con METRICS_CONFIG.slaLimits y con el
      // `slaSummary` del dashboard en index.html (A=3, AA=14, AAA=30).
      addRulePair("A", METRICS_CONFIG.slaLimits.A, 1);     // Verde < 2, Amarillo 2-3, Rojo > 3
      addRulePair("AA", METRICS_CONFIG.slaLimits.AA, 2);   // Verde < 12, Amarillo 12-14, Rojo > 14
      addRulePair("AAA", METRICS_CONFIG.slaLimits.AAA, 5); // Verde < 25, Amarillo 25-30, Rojo > 30
  });

  sheet.setConditionalFormatRules(newRules.concat(cleanRules));
  return true;
}

function setupConditionalFormatting() {
  const ui = SpreadsheetApp.getUi();
  const excludedSheets = [
      APP_CONFIG.logSheetName.toUpperCase(),
      APP_CONFIG.salesSheetName.toUpperCase(),
      APP_CONFIG.draftSheetName.toUpperCase()
  ];

  const allSheets = SS.getSheets();
  let logMsg = "";
  let count = 0;

  allSheets.forEach(sheet => {
    const sName = sheet.getName().trim();
    const sNameUpper = sName.toUpperCase();

    if (excludedSheets.includes(sNameUpper)) return;

    // Delegamos a la nueva función robusta
    if (applyTrafficLightToSheet(sheet)) {
       logMsg += `✅ ${sName}\n`;
       count++;
    }
  });

  if (count > 0) {
      ui.alert(`Semaforización aplicada a ${count} hojas:\n${logMsg}`);
  } else {
      ui.alert("⚠️ No se encontraron hojas aptas (con columnas CLASIFICACION y FECHA) para aplicar formato.");
  }
}

function colIndexToLetter(col) {
  let temp, letter = '';
  while (col > 0) {
    temp = (col - 1) % 26;
    letter = String.fromCharCode(temp + 65) + letter;
    col = (col - temp - 1) / 26;
  }
  return letter;
}

function test_NumericSequence_Generation() {
  console.log("🛠️ INICIANDO TEST: Generación de Secuencia Numérica");
  try {
      const lock = LockService.getScriptLock();
      const props = PropertiesService.getScriptProperties();

      // Mock properties for testing if not set
      if (!props.getProperty('ANTONIA_SEQ')) {
          props.setProperty('ANTONIA_SEQ', '1000');
          console.log("Inicializando ANTONIA_SEQ a 1000 para prueba.");
      }

      const val1 = generateNumericSequence('ANTONIA_SEQ');
      const val2 = generateNumericSequence('ANTONIA_SEQ');

      console.log("Valor 1:", val1);
      console.log("Valor 2:", val2);

      if (Number(val2) === Number(val1) + 1) {
          console.log("✅ Secuencia incrementa correctamente.");
      } else {
          console.error("❌ Secuencia falló en incrementar.");
      }

      if (!isNaN(val1)) {
          console.log("✅ El folio es numérico.");
      } else {
          console.error("❌ El folio NO es numérico.");
      }

  } catch (e) {
      console.error("❌ Error en prueba:", e);
  }
}

function test_Antonia_Distribution_Manual() {
  console.log("🛠️ INICIANDO TEST: Distribución Manual Antonia -> Vendedor");

  // 1. Datos simulados
  const taskData = {
    FOLIO: "TEST-DIST-" + new Date().getTime(),
    CONCEPTO: "PRUEBA DISTRIBUCION",
    VENDEDOR: "TEST_USER (VENTAS)", // Asume que existe hoja TEST_USER (VENTAS) o similar
    ESTATUS: "COTIZADA"
  };

}

function apiFetchInfoBankData(year, monthName, companyName, folderName) {
  try {
    const sheetName = "ANTONIA_VENTAS";
    const res = internalFetchSheetData(sheetName);
    if (!res.success) return { success: false, message: res.message };

    const monthMap = {
        'ENERO': 0, 'FEBRERO': 1, 'MARZO': 2, 'ABRIL': 3, 'MAYO': 4, 'JUNIO': 5,
        'JULIO': 6, 'AGOSTO': 7, 'SEPTIEMBRE': 8, 'OCTUBRE': 9, 'NOVIEMBRE': 10, 'DICIEMBRE': 11
    };
    const targetMonth = monthMap[String(monthName).toUpperCase().trim()];
    const targetYear = parseInt(year) || 2025;
    const targetCompany = String(companyName).toUpperCase().trim();

    if (targetMonth === undefined) return { success: false, message: "Mes inválido" };

    // Filtrar datos
    const filtered = res.data.filter(row => {
       // Helper para buscar valores insensible a mayúsculas
       const keys = Object.keys(row);
       const upperKeys = keys.map(k => k.toUpperCase().trim());
       const getVal = (targetKeys) => {
           for (const t of targetKeys) {
               const idx = upperKeys.indexOf(t);
               if (idx > -1) return row[keys[idx]];
           }
           return null;
       };

       // 1. Company Match (Loose)
       const rowClient = String(getVal(['CLIENTE']) || '').toUpperCase().trim();
       if (!rowClient) return false;
       
       // Check bidirectional inclusion to handle variations
       if (!rowClient.includes(targetCompany) && !targetCompany.includes(rowClient)) return false;

       // 2. Date Match (Prioridad: F. INICIO)
       // El periodo lo manda F. INICIO (decisión del dueño); FECHA/ALTA solo
       // como respaldo para las hojas que no tienen columna de inicio.
       const dateVal = getVal(BANK_DATE_ALIASES);

       if (!dateVal) return false;
       
       let dObj = null;
       if (dateVal instanceof Date) {
           dObj = dateVal;
       } else {
           // Try parsing string dd/mm/yy
           const parts = String(dateVal).split('/');
           if (parts.length === 3) {
               let y = parseInt(parts[2]);
               if (y < 100) y += 2000;
               dObj = new Date(y, parseInt(parts[1])-1, parseInt(parts[0]));
           }
       }
       
       if (!dObj || isNaN(dObj.getTime())) return false;
       if (dObj.getMonth() !== targetMonth) return false;
       if (dObj.getFullYear() !== targetYear) return false;

       return true;
    });

    // NORMALIZACION DE DATOS PARA EL FRONTEND (SOLICITUD USUARIO)
    const mappedData = filtered.map(row => {
       const keys = Object.keys(row);
       const upperKeys = keys.map(k => k.toUpperCase().trim());
       const getVal = (targetKeys) => {
           for (const t of targetKeys) {
               const idx = upperKeys.indexOf(t);
               if (idx > -1) return row[keys[idx]];
           }
           return "";
       };

       return {
           'FECHA_INICIO': getVal(BANK_DATE_ALIASES),
           'AREA': getVal(['AREA', 'DEPARTAMENTO', 'ESPECIALIDAD']),
           'CONCEPTO': getVal(['CONCEPTO', 'DESCRIPCION', 'DESCRIPCIÓN', 'ACTIVIDAD']),
           'VENDEDOR': getVal(['VENDEDOR', 'RESPONSABLE', 'ENCARGADO', 'INVOLUCRADOS']),
           'ESTATUS': getVal(['ESTATUS', 'STATUS', 'ESTADO']),
           'FOLIO': getVal(['FOLIO', 'ID']),
           'COTIZACION': getVal(['COTIZACION', 'ARCHIVO', 'LINK', 'URL', 'PDF'])
       };
    });

    return { success: true, data: mappedData };
  } catch(e) {
    return { success: false, message: e.toString() };
  }
}
function apiFetchDistinctClients() {
  try {
    const sheetName = "ANTONIA_VENTAS";
    const res = internalFetchSheetData(sheetName);
    if (!res.success) return { success: false, message: res.message };

    const clients = new Set();
    
    // Add existing static list for robustness (optional, but good practice to not lose hardcoded ones if needed)
    // Actually, user said "I need all those from the ANTONIA_VENTAS list", implying dynamic. 
    // Let's check headers to find 'CLIENTE'
    // internalFetchSheetData returns objects with keys uppercased and trimmed.
    
    res.data.forEach(row => {
        if (row['CLIENTE']) {
            const c = String(row['CLIENTE']).trim().toUpperCase();
            if (c) clients.add(c);
        }
    });

    const sortedClients = Array.from(clients).sort();
    return { success: true, data: sortedClients };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

function apiSaveTrackerBatch(personName, tasks, username) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(30000)) {
    try {
      const processedTasks = [];
      const distributionTasks = [];

      // RUTEO PROTEGIDO DE VENTAS ("La Ley de Antonia", AGENTS.md §3)
      const routing = resolveTrackerTarget(personName, username);
      if (routing.redirected) {
          registrarLog(username || "DESCONOCIDO", "RUTEO_PROTEGIDO",
              `${personName} -> ${routing.sheet} (${routing.reason})`);
      }
      personName = routing.sheet;

      const isAntonia = String(personName).toUpperCase() === "ANTONIA_VENTAS";

      // Sequence Logic for Antonia
      let currentSeq = null;
      let seqKey = 'ANTONIA_SEQ';
      const antoniaPrefix = generatePrefix(personName);
      if (isAntonia) {
          const props = PropertiesService.getScriptProperties();
          currentSeq = Number(props.getProperty(seqKey) || 1000);

          // AUTO-HEALING: Scan batch for higher existing IDs to sync sequence
          // (soporta folios con prefijo, ej. "AV-1042")
          tasks.forEach(t => {
              const rawFolio = String(t['FOLIO'] || t['ID'] || "").replace(/^[A-Z]+-/i, "");
              const fid = parseInt(rawFolio, 10);
              if (!isNaN(fid) && fid > currentSeq) {
                  currentSeq = fid;
              }
          });
      }

      tasks.forEach(task => {
        let taskData = {...task};

        if (isAntonia) {
             if (!taskData['FOLIO'] && !taskData['ID']) {
                 // GHOST BUSTING: Verificar contenido antes de asignar Folio
                 const clean = (val) => val ? String(val).trim() : "";
                 const c = clean(taskData['CONCEPTO']);
                 const d = clean(taskData['DESCRIPCION']);
                 const cl = clean(taskData['CLIENTE']);
                 const v = clean(taskData['VENDEDOR']);

                 // Ignorar si VENDEDOR es solo el default "ANTONIA_VENTAS" y no hay nada más
                 const isVendedorDefault = v.toUpperCase() === "ANTONIA_VENTAS";

                 const hasContent = (c !== "") ||
                                    (d !== "") ||
                                    (cl !== "") ||
                                    (v !== "" && !isVendedorDefault);

                 if (!hasContent) return; // SKIP EMPTY ROWS (Don't process, don't distribute)

                 currentSeq++;
                 taskData['FOLIO'] = antoniaPrefix + String(currentSeq);
             } else {
                 // RESTRICTIONS FOR EXISTING TASKS
                 const allowedBase = ['FOLIO', 'ID', 'ESTATUS', 'STATUS', 'AVANCE', 'AVANCE %', '_rowIndex', 'VENDEDOR', 'RESPONSABLE', 'INVOLUCRADOS', 'ENCARGADO', 'CONCEPTO', 'DESCRIPCION', 'CLIENTE', 'COTIZACION', 'F2', 'LAYOUT', 'TIMELINE', 'AREA', 'CLASIFICACION', 'CLASI', 'DIAS', 'RELOJ', 'ESPECIALIDAD',
                     // Timeline de la Papa Caliente (delegación de fases)
                     'PROCESO', 'PROCESO_LOG', 'MAP COT', 'ETAPA', 'FASE'];
                 Object.keys(taskData).forEach(key => {
                     const kUp = key.toUpperCase();
                     if (key.startsWith('_')) return;
                     const isBase = allowedBase.includes(kUp);
                     const isDate = kUp.includes('FECHA') || kUp.includes('ALTA');
                     if (!isBase && !isDate) {
                         delete taskData[key];
                     }
                 });
             }
             // DISTRIBUCIÓN LATERAL ("Papa Caliente"): delega la fase y actualiza el timeline
             try { internalApplyHotPotato(personName, taskData, username, false); }
             catch (e) { console.warn("Papa Caliente: " + e.toString()); }

             // Prepare distribution data
             const distData = JSON.parse(JSON.stringify(taskData));
             delete distData._rowIndex;
             distributionTasks.push(distData);
        } else if (String(personName).toUpperCase().includes("(VENTAS)")) {
             // REVERSE SYNC PREPARATION
             const distData = JSON.parse(JSON.stringify(taskData));
             delete distData._rowIndex;
             distributionTasks.push(distData);
        }
        processedTasks.push(taskData);
      });

      // Save Sequence
      if (isAntonia && currentSeq !== null) {
           const props = PropertiesService.getScriptProperties();
           props.setProperty(seqKey, String(currentSeq));
      }

      // Batch Update Main Sheet
      const res = internalBatchUpdateTasks(personName, processedTasks, false); // Already locked

      if (res.success) {
          // Handle Distribution for Antonia
          if (isAntonia && distributionTasks.length > 0) {
              // Group by vendor to batch updates
              const byVendor = {};
              distributionTasks.forEach(t => {
                  const vendedorKey = Object.keys(t).find(k => k.toUpperCase().trim() === "VENDEDOR");
                  if (vendedorKey && t[vendedorKey]) {
                       const vName = String(t[vendedorKey]).trim();
                       if (vName.toUpperCase() !== "ANTONIA_VENTAS") {
                           let target = vName;
                           // Logic to find target sheet (suffix check)
                           let finalTarget = null;
                           if (target.toUpperCase().includes("(VENTAS)")) finalTarget = target;
                           else {
                               if (findSheetSmart(target + " (VENTAS)")) finalTarget = target + " (VENTAS)";
                           }

                           if (finalTarget) {
                               if (!byVendor[finalTarget]) byVendor[finalTarget] = [];
                               byVendor[finalTarget].push(t);
                           }
                       }
                  }
              });

              // Execute distribution batches
              for (const [vSheet, vTasks] of Object.entries(byVendor)) {
                   internalBatchUpdateTasks(vSheet, vTasks, false);
              }

              // Sync to ADMIN
              internalBatchUpdateTasks("ADMINISTRADOR", distributionTasks, false);
          }

          // Handle Reverse Sync (Vendor -> Antonia)
          // Sanea ESTATUS/AVANCE/CUMPLIMIENTO y cierra la fase en el timeline.
          if (String(personName).toUpperCase().includes("(VENTAS)") && !isAntonia && distributionTasks.length > 0) {
               internalReverseSyncToAntonia(personName, distributionTasks, username, false);
          }

          registrarLog(username, "BATCH_UPDATE", `Actualizadas ${tasks.length} tareas en ${personName}`);
      }

      // AGENTS.md §2: se devuelve el objeto completo para que el frontend
      // lo fusione y marque _isNew = false.
      return {
          success: true,
          message: "Guardado exitoso",
          data: (res && res.data) ? res.data : processedTasks,
          routing: routing.redirected ? routing : null
      };

    } catch (e) {
      return { success: false, message: e.toString() };
    } finally {
      lock.releaseLock();
    }
  } else {
      return { success: false, message: "Sistema ocupado" };
  }
}

/**
 * Columnas por las que se coloca cada origen en el calendario del dashboard.
 * Una actividad del tracker va por su FECHA; una cotización, por su F. INICIO
 * (decisión del dueño, 2026-08-15). `quotes` tiene además F. VISITA y
 * F. ENTREGA, así que tomar "la primera fecha que aparezca" la pondría en un
 * día que no es el que se trabaja.
 */
const CALENDAR_DATE_ALIASES = {
  TRACKER: ["FECHA", "FECHA ALTA", "FECHA_ALTA", "FECHA DE ALTA"],
  COTIZACIONES: ["F. INICIO", "F INICIO", "F_INICIO", "FECHA INICIO", "FECHA_INICIO", "FECHA DE INICIO"],
  PERSONAL: ["FECHA", "FECHA ALTA", "FECHA_ALTA"]
};

/**
 * Fecha con la que el Banco de Cotizaciones agrupa una cotización por mes y año.
 * Es la del calendario más FECHA/ALTA al final, como respaldo para las hojas
 * creadas con DEFAULT_SALES_HEADERS, que no tienen columna de inicio.
 */
const BANK_DATE_ALIASES = CALENDAR_DATE_ALIASES.COTIZACIONES.concat(
  ["FECHA", "ALTA", "FECHA ALTA"]);

/** Día ISO (YYYY-MM-DD) en el que se pinta una fila, o "" si no trae su fecha. */
function calendarDate(row, origen) {
  const aliases = CALENDAR_DATE_ALIASES[String(origen || "").toUpperCase().trim()];
  if (!aliases) return "";
  const valor = pickTaskValue(row, aliases);
  if (!valor) return "";
  let d = null;
  if (valor instanceof Date) {
    d = valor;
  } else {
    const texto = String(valor).trim();
    const iso = texto.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) return iso[1] + "-" + iso[2] + "-" + iso[3];
    const dmy = texto.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
    if (dmy) {
      const y = dmy[3].length === 2 ? "20" + dmy[3] : dmy[3];
      d = new Date(Number(y), Number(dmy[2]) - 1, Number(dmy[1]));
    }
  }
  if (!d || isNaN(d.getTime())) return "";
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}

/**
 * ¿Esta fila es trabajo de esta persona?
 *
 * La regla del calendario: aparece si es RESPONSABLE o VENDEDOR, no por haberla
 * asignado. Una fila sin responsable cuenta como propia de la hoja en la que
 * está — no hay nadie más a quien pueda pertenecer.
 */
function isResponsibleFor(row, personName) {
  const quien = normalizeStaffName(personName);
  if (!quien) return false;
  const crudo = pickTaskValue(row, ["RESPONSABLE", "RESPONSABLES", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO"]);
  if (!crudo) return true;
  const asignados = String(crudo).replace(/\n/g, ",").replace(/;/g, ",").split(",")
    .map(n => normalizeStaffName(n)).filter(n => n);
  if (!asignados.length) return true;
  return asignados.indexOf(quien) !== -1;
}

function apiFetchCombinedCalendarData(sheetName) {
  try {
      const results = [];
      const baseName = String(sheetName).replace(/\s*\(VENTAS\)/i, "").trim();
      // Si es ANTONIA_VENTAS, sus cotizaciones viven en la hoja maestra.
      const targets = (baseName.toUpperCase() === "ANTONIA_VENTAS")
        ? [{ hoja: "ANTONIA_VENTAS", origen: "COTIZACIONES" }]
        : [{ hoja: baseName, origen: "TRACKER" },
           { hoja: baseName + " (VENTAS)", origen: "COTIZACIONES" }];

      targets.forEach(t => {
          const res = internalFetchSheetData(t.hoja);
          if (res.success && res.data) {
              res.data.forEach(row => {
                  // Solo lo que esta persona trabaja: quien reparte una
                  // actividad no la ve en su propio calendario.
                  if (!isResponsibleFor(row, baseName)) return;
                  results.push(Object.assign({}, row, {
                      ORIGEN: t.origen,
                      FECHA_CALENDARIO: calendarDate(row, t.origen)
                  }));
              });
          }
      });

      // --- ADDED: Personal Agenda Integration for Dashboard ---
      const personalRes = internalFetchSheetData("AGENDA_PERSONAL");
      if (personalRes.success && personalRes.data) {
          const myEvents = personalRes.data.filter(e => normalizeStaffName(e.USUARIO) === normalizeStaffName(baseName));
          const mappedEvents = myEvents.map(e => ({
              ...e,
              CONCEPTO: e.TITULO || e.CONCEPTO,
              CLIENTE: "PERSONAL",
              ORIGEN: "PERSONAL",
              FECHA_CALENDARIO: calendarDate(e, "PERSONAL")
          }));
          results.push(...mappedEvents);
      }
      // --------------------------------------------------------

      // Deduplicate by ORIGEN + ID/FOLIO: una cotización y la actividad que la
      // acompaña pueden compartir folio y son dos filas del calendario.
      const uniqueTasks = {};
      results.forEach(r => {
          const id = r.ID || r.FOLIO || (r.CONCEPTO ? r.CONCEPTO + r.FECHA : null);
          if (id) uniqueTasks[(r.ORIGEN || "") + "::" + id] = r;
      });

      const finalData = Object.values(uniqueTasks);

      // Simple Sort by Date string (DD/MM/YY) if possible, else original order
      // internalFetchSheetData already sorts by date desc.
      // Merging two sorted lists... roughly fine.

      return { success: true, data: finalData };
  } catch(e) {
      return { success: false, message: e.toString() };
  }
}

/**
 * ======================================================================
 * MODULO: AGENDA PERSONAL (HOLTZAR INTEGRATION)
 * ======================================================================
 */

function apiFetchUnifiedAgenda(username) {
  // 1. Fetch Work Tasks (Existing Logic)
  let workTasks = [];
  try {
     // Determine target for work tasks based on role/user
     let target = username;
     if (String(username).toUpperCase() === 'ANTONIA_VENTAS') target = "ANTONIA_VENTAS";

     const workRes = apiFetchCombinedCalendarData(target);
     if (workRes.success) {
         // Filter out Personal Events to avoid duplication (fetched separately below)
         workTasks = workRes.data.filter(t => t.CLIENTE !== "PERSONAL");
     }
  } catch(e) { console.error("Error fetching work tasks", e); }

  // 2. Fetch Personal Events
  let personalEvents = [];
  try {
     const sheet = findSheetSmart("AGENDA_PERSONAL");
     if (sheet) {
        const res = internalFetchSheetData("AGENDA_PERSONAL");
        if(res.success) {
            // Filter by user if possible, for now return all found
            personalEvents = res.data.filter(r => !r.USUARIO || r.USUARIO === username);
        }
     } else {
        // MOCK DATA FOR DEMO IF SHEET DOESN'T EXIST
        const today = new Date();
        const y = today.getFullYear();
        const m = today.getMonth(); // 0-indexed
        const d = today.getDate();

        personalEvents = [
            { ID: 'P-1', TITULO: 'Rutina Mañana', TIPO: 'PERSONAL', HORA_INICIO: '06:00', HORA_FIN: '07:00', DETALLES: 'Meditación y Café', FECHA: new Date(y, m, d), CLASIFICACION: 'PERSONAL' },
            { ID: 'P-2', TITULO: 'Gimnasio', TIPO: 'PERSONAL', HORA_INICIO: '07:30', HORA_FIN: '08:30', DETALLES: 'Cardio', FECHA: new Date(y, m, d), CLASIFICACION: 'SALUD' },
            { ID: 'P-3', TITULO: 'Comida', TIPO: 'COMIDA', HORA_INICIO: '14:00', HORA_FIN: '15:00', DETALLES: 'Pollo y Arroz', FECHA: new Date(y, m, d), CLASIFICACION: 'SALUD' }
        ];
     }
  } catch(e) { console.error("Error fetching personal events", e); }

  // 3. Fetch Habits
  let habits = [];
  try {
      const sheet = findSheetSmart("HABITOS_LOG");
      if (sheet) {
         const res = internalFetchSheetData("HABITOS_LOG");
         if (res.success) habits = res.data.filter(r => !r.USUARIO || r.USUARIO === username);
      } else {
         // MOCK DATA
         habits = [
             { ID: 'H1', HABITO: 'Leer 30min', META: 5, LOG_JSON: JSON.stringify([true, true, false, true, false, false, false]) },
             { ID: 'H2', HABITO: 'Ejercicio', META: 4, LOG_JSON: JSON.stringify([false, true, true, false, false, false, false]) },
             { ID: 'H3', HABITO: 'Meditar', META: 7, LOG_JSON: JSON.stringify([true, true, true, true, true, false, false]) }
         ];
      }
  } catch(e) { console.error("Error fetching habits", e); }

  return { success: true, workTasks: workTasks, personalEvents: personalEvents, habits: habits };
}

function apiSavePersonalEvent(eventData) {
    // Ensure sheet exists
    let sheet = findSheetSmart("AGENDA_PERSONAL");
    if (!sheet) {
        sheet = SS.insertSheet("AGENDA_PERSONAL");
        sheet.appendRow(["ID", "USUARIO", "TITULO", "TIPO", "FECHA", "HORA_INICIO", "HORA_FIN", "DETALLES", "CLASIFICACION", "ESTATUS"]);
    }
    return internalBatchUpdateTasks("AGENDA_PERSONAL", [eventData]);
}

function apiSaveHabitLog(habitData) {
    // Ensure sheet exists
    let sheet = findSheetSmart("HABITOS_LOG");
    if (!sheet) {
        sheet = SS.insertSheet("HABITOS_LOG");
        sheet.appendRow(["ID", "USUARIO", "HABITO", "META", "LOG_JSON", "FECHA_ACTUALIZACION"]);
    }
    // If saving a habit update, we might need to find the existing row.
    // internalBatchUpdateTasks handles updates by ID/FOLIO.
    return internalBatchUpdateTasks("HABITOS_LOG", [habitData]);
}

/**
 * Jutsu de Transcripción con Gemini Flash
 */
function transcribirConGemini(base64Audio, mimeType) {
  // IMPORTANTE: Reemplazar con la API Key real del proyecto
  const API_KEY = "AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc";

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${API_KEY}`;

  const payload = {
    contents: [{
      parts: [
        { text: "Transcribe el siguiente audio exactamente como se escucha. Corrige ortografía básica. Solo dame el texto limpio en español." },
        {
          inline_data: {
            mime_type: mimeType || "audio/mp3",
            data: base64Audio
          }
        }
      ]
    }]
  };

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  try {
    const response = UrlFetchApp.fetch(url, options);
    const json = JSON.parse(response.getContentText());

    if (json.candidates && json.candidates[0].content) {
      return json.candidates[0].content.parts[0].text;
    } else {
      return "Error: No pude escuchar el audio claramente.";
    }
  } catch (e) {
    return "Error en el sistema: " + e.toString();
  }
}

/**
 * JUTSU DE AUTORIZACIÓN FORZADA
 * Ejecuta esto manualmente desde el editor en la PC una vez.
 */
function forzarPermisos() {
  console.log("Concentrando chakra para conectar con el exterior...");
  // Solo llamamos a esto para que Google detecte que necesitamos el permiso
  // No importa si falla la URL, lo que importa es que pida el permiso.
  try {
    UrlFetchApp.fetch("https://www.google.com");
    console.log("¡Conexión establecida! Chakra fluyendo.");
  } catch (e) {
    console.log("Error (esperado si no hay internet, pero ya tienes permisos): " + e.toString());
  }
}

/**
 * ======================================================================
 * MÓDULO DE PARIDAD DE MIGRACIÓN — HOLTMONT
 * ======================================================================
 * Funcionalidades que existían en el frontend / plan de negocio y que
 * faltaban en el backend GAS tras la migración a Python:
 *
 *   A. Utilidades de nombre, correo y prefijos de folio
 *   B. Ruteo protegido de ventas ("La Ley de Antonia")
 *   C. Evaluación de progreso y estatus terminales
 *   D. Papa Caliente (PROCESO_LOG / MAP COT) y Reverse Sync
 *   E. NotifierService (Make.com -> Outlook)
 *   F. Agente de métricas de cotizaciones (reglas + Gemini)
 *   G. APIs sueltas que invoca index.html
 *
 * Todas las funciones son globales para que `google.script.run` las vea.
 * Ver AGENTS.md §§2-5 para las reglas de negocio que implementan.
 */

// ----------------------------------------------------------------------
// A. NOMBRES, CORREOS Y PREFIJOS DE FOLIO
// ----------------------------------------------------------------------

/** Normaliza un nombre de usuario/hoja: quita guiones bajos y el sufijo (VENTAS). */
function normalizeStaffName(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(/\s*\(VENTAS\)/ig, " ")
    .replace(/[_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
}

/** Lee un valor del payload sin importar mayúsculas/minúsculas de la clave. */
function pickTaskValue(task, keys) {
  if (!task) return "";
  const wanted = keys.map(k => String(k).toUpperCase().trim());
  const taskKeys = Object.keys(task);
  for (let w = 0; w < wanted.length; w++) {
    for (let i = 0; i < taskKeys.length; i++) {
      if (String(taskKeys[i]).toUpperCase().replace(/\n/g, ' ').replace(/\s+/g, ' ').trim() === wanted[w]) {
        const val = task[taskKeys[i]];
        if (val !== undefined && val !== null && val !== "") return val;
      }
    }
  }
  return "";
}

/**
 * GENERADOR DE PREFIJOS DE FOLIO
 * Usuarios conocidos usan sus iniciales oficiales (JO-, JC-, LC-, AV-, ...).
 * Cualquier otro nombre genera iniciales dinámicas (MIGUEL GALLARDO -> MG-).
 * Ante nombre vacío o error retorna siempre el fallback seguro "PPC-".
 */
function generatePrefix(name) {
  try {
    const raw = normalizeStaffName(String(name === null || name === undefined ? "" : name).replace(/[\-.]+/g, " "));
    if (!raw) return FOLIO_PREFIX_FALLBACK;
    if (Object.prototype.hasOwnProperty.call(FOLIO_PREFIX_MAP, raw)) {
      return FOLIO_PREFIX_MAP[raw] + "-";
    }
    const words = raw.split(" ").filter(w => w && FOLIO_STOPWORDS.indexOf(w) === -1);
    if (words.length === 0) return FOLIO_PREFIX_FALLBACK;
    const candidate = (words.length === 1)
      ? words[0].substring(0, 2)
      : words[0].charAt(0) + words[1].charAt(0);
    // Un prefijo debe empezar con letra: nombres numéricos caen al fallback.
    if (!/^[A-ZÑ][A-ZÑ0-9]?$/.test(candidate)) return FOLIO_PREFIX_FALLBACK;
    return candidate + "-";
  } catch (e) {
    console.warn("generatePrefix fallback: " + e.toString());
    return FOLIO_PREFIX_FALLBACK;
  }
}

/** Clave de secuencia por hoja (las tablas (VENTAS) comparten la del titular). */
function folioSequenceKey(sheetName) {
  const base = normalizeStaffName(sheetName) || "GENERAL";
  if (base === "ANTONIA VENTAS") return "ANTONIA_SEQ";
  return "SEQ_" + base.replace(/\s+/g, "_");
}

/** Folio completo para una hoja: prefijo del titular + consecutivo. */
function generateFolioForSheet(sheetName) {
  return generatePrefix(sheetName) + generateNumericSequence(folioSequenceKey(sheetName));
}

/** Correo corporativo de un usuario (USER_DB primero, derivado después). */
function resolveUserEmail(name) {
  try {
    const clean = normalizeStaffName(name);
    if (!clean) return "";
    const dbKey = clean.replace(/\s+/g, "_");
    if (Object.prototype.hasOwnProperty.call(USER_DB, dbKey) && USER_DB[dbKey].email) {
      return USER_DB[dbKey].email;
    }
    // Derivación estándar nombre.apellido@holtmont.com para el resto del directorio
    const words = clean.split(" ").filter(w => w && FOLIO_STOPWORDS.indexOf(w) === -1);
    if (words.length === 0) return "";
    const slug = (words.length === 1)
      ? words[0]
      : words[0] + "." + words[words.length - 1];
    return slug
      .toLowerCase()
      .replace(/[ÁÀÄÂ]/gi, "a").replace(/[ÉÈËÊ]/gi, "e").replace(/[ÍÌÏÎ]/gi, "i")
      .replace(/[ÓÒÖÔ]/gi, "o").replace(/[ÚÙÜÛ]/gi, "u").replace(/Ñ/gi, "n")
      .replace(/[^a-z0-9.]/g, "") + "@" + NOTIFIER_CONFIG.domain;
  } catch (e) {
    return "";
  }
}

// ----------------------------------------------------------------------
// B. RUTEO PROTEGIDO DE VENTAS ("LA LEY DE ANTONIA")
// ----------------------------------------------------------------------

/**
 * Resuelve a qué hoja debe escribirse realmente una tarea.
 *  - Solo ANTONIA_VENTAS puede escribir en el core de ventas; a cualquier
 *    otro usuario se le redirige a su tracker personal.
 *  - El sufijo "(VENTAS)" solo lo respetan Toñita y el propio titular de
 *    la hoja; para el resto se purga globalmente.
 * @returns {{sheet: string, redirected: boolean, reason: string}}
 */
function resolveTrackerTarget(personName, username) {
  const original = String(personName === null || personName === undefined ? "" : personName).trim();
  const user = normalizeStaffName(username);
  const isAntoniaUser = (user === "ANTONIA VENTAS");

  if (original.toUpperCase().trim() === SALES_ROUTING_CONFIG.masterSalesSheet.toUpperCase() && !isAntoniaUser) {
    return { sheet: SALES_ROUTING_CONFIG.antoniaPersonalSheet, redirected: true, reason: "CORE_VENTAS_PROTEGIDO" };
  }

  const base = original.replace(/\s*\(VENTAS\)/ig, "").trim();
  if (base !== original) {
    const isOwner = (normalizeStaffName(base) === user && user !== "");
    if (!isAntoniaUser && !isOwner) {
      return { sheet: base, redirected: true, reason: "SUFIJO_VENTAS_PURGADO" };
    }
  }
  return { sheet: original, redirected: false, reason: "" };
}

/** ¿La hoja destino es una tabla de ventas (core o con sufijo)? */
function isSalesSheet(sheetName) {
  const up = String(sheetName || "").toUpperCase();
  return up === SALES_ROUTING_CONFIG.masterSalesSheet.toUpperCase() || up.indexOf("(VENTAS)") > -1;
}

// ----------------------------------------------------------------------
// C. PROGRESO Y ESTATUS
// ----------------------------------------------------------------------

/**
 * Evalúa si un valor de AVANCE representa el 100 %.
 * AGENTS.md §4: el número nativo 1 (celda con formato porcentaje) SÍ es 100 %,
 * pero el string "1" o "1.0" (que el usuario teclea como 1 %) NO lo es.
 */
function isProgressComplete(value) {
  if (value === null || value === undefined || value === "") return false;
  if (value instanceof Date) return false;
  if (typeof value === "number") {
    return Math.abs(value - 1) < 0.001 || Math.abs(value - 100) < 0.01;
  }
  const raw = String(value).trim();
  if (!raw) return false;
  const clean = raw.replace("%", "").replace(",", ".").trim();
  const num = parseFloat(clean);
  if (isNaN(num)) return false;
  return Math.abs(num - 100) < 0.01;
}

/** Estatus que cierran una tarea o cotización (archivado y métricas). */
function isTerminalStatus(value) {
  const up = String(value === null || value === undefined ? "" : value).toUpperCase().trim();
  if (!up) return false;
  if (TERMINAL_STATUSES.indexOf(up) > -1) return true;
  return WIN_STATUSES.concat(LOSS_STATUSES).some(s => up.indexOf(s) === 0);
}

/** Clasifica el estatus de una cotización para las métricas. */
function classifyQuoteStatus(value) {
  const up = String(value === null || value === undefined ? "" : value).toUpperCase().trim();
  if (!up) return "EN_PROCESO";
  if (WIN_STATUSES.some(s => up.indexOf(s) === 0)) return "GANADA";
  if (LOSS_STATUSES.some(s => up.indexOf(s) === 0)) return "PERDIDA";
  return "EN_PROCESO";
}

/** Normaliza una celda para comparaciones (fechas -> dd/MM/yy). */
function normalizeCellValue(value) {
  if (value === null || value === undefined) return "";
  if (value instanceof Date) {
    return Utilities.formatDate(value, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
  }
  const raw = String(value).trim();
  const m = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (m) {
    const yy = m[3].length === 4 ? m[3].slice(-2) : m[3];
    return String(m[1]).padStart(2, "0") + "/" + String(m[2]).padStart(2, "0") + "/" + yy;
  }
  const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return iso[3] + "/" + iso[2] + "/" + iso[1].slice(-2);
  return raw.toUpperCase().replace(/\s+/g, " ").trim();
}

/** Convierte un valor de celda a Date (soporta dd/MM/yy y ISO). */
function parseSheetDate(value) {
  try {
    if (!value) return null;
    if (value instanceof Date) return isNaN(value.getTime()) ? null : value;
    const raw = String(value).trim();
    const m = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
    if (m) {
      let y = parseInt(m[3], 10);
      if (y < 100) y += 2000;
      return new Date(y, parseInt(m[2], 10) - 1, parseInt(m[1], 10));
    }
    const d = new Date(raw);
    return isNaN(d.getTime()) ? null : d;
  } catch (e) {
    return null;
  }
}

// ----------------------------------------------------------------------
// D. PAPA CALIENTE (PROCESO_LOG / MAP COT) Y REVERSE SYNC
// ----------------------------------------------------------------------

/** Parsea PROCESO_LOG de forma tolerante (siempre retorna array). */
function parseProcesoLog(value) {
  try {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    const parsed = JSON.parse(String(value));
    return Array.isArray(parsed) ? parsed : [];
  } catch (e) {
    return [];
  }
}

/** 'CD' o 'Calculo y Diseño' -> 'CD'. Retorna "" si no es una fase válida. */
function normalizePhaseId(value) {
  const raw = String(value === null || value === undefined ? "" : value).trim();
  if (!raw) return "";
  const up = raw.toUpperCase();
  if (PROCESS_STEPS.indexOf(up) > -1) return up;
  for (let i = 0; i < PROCESS_STEPS.length; i++) {
    const step = PROCESS_STEPS[i];
    if (FULL_PROCESS_NAMES[step].toUpperCase() === up) return step;
  }
  // Formatos tipo "🔴 CD" o "🟢 L | 🔴 CD | ⚪ EP"
  const match = raw.match(/[🔴🟡]\s*([A-Z]{1,3})/);
  if (match && PROCESS_STEPS.indexOf(match[1]) > -1) return match[1];
  return "";
}

/** Nombre completo de la fase ('CD' -> 'Calculo y Diseño'). */
function phaseLabel(stepId) {
  const id = normalizePhaseId(stepId);
  return (id && FULL_PROCESS_NAMES[id]) ? FULL_PROCESS_NAMES[id] : String(stepId || "");
}

/** Extrae la fase marcada en un concepto: '... [Calculo y Diseño]' -> 'CD'. */
function extractPhaseFromConcepto(concepto) {
  const raw = String(concepto === null || concepto === undefined ? "" : concepto);
  const matches = raw.match(/\[([^\]]+)\]/g);
  if (!matches) return "";
  for (let i = matches.length - 1; i >= 0; i--) {
    const inner = matches[i].replace(/^\[|\]$/g, "").trim();
    const id = normalizePhaseId(inner);
    if (id) return id;
  }
  return "";
}

/** Quita las marcas de fase de un concepto delegado. */
function stripPhaseMarker(concepto) {
  return String(concepto === null || concepto === undefined ? "" : concepto)
    .replace(/\s*\[[^\]]+\]\s*$/g, "")
    .trim();
}

/**
 * Construye la columna MAP COT con la convención del visualizador:
 *   🟢 etapa terminada · 🔴 etapa en curso · ⚪ etapa pendiente
 */
function buildMapCot(log, currentStep) {
  const entries = parseProcesoLog(log);
  const current = normalizePhaseId(currentStep);
  const currentIdx = PROCESS_STEPS.indexOf(current);

  return PROCESS_STEPS.map((step, idx) => {
    const stepEntries = entries.filter(e => e && (e.step === step || e.to === step));
    if (stepEntries.length > 0) {
      const allDone = stepEntries.every(e => String(e.status || "").toUpperCase() === "DONE");
      return (allDone ? "🟢 " : "🔴 ") + step;
    }
    if (currentIdx > -1 && idx < currentIdx) return "🟢 " + step;
    if (step === current) return "🔴 " + step;
    return "⚪ " + step;
  }).join(" | ");
}

/** Marca una fase del PROCESO_LOG para un responsable dado. */
function upsertProcesoLogEntry(log, stepId, assignee, status) {
  const entries = parseProcesoLog(log);
  const step = normalizePhaseId(stepId);
  if (!step) return entries;
  const who = String(assignee || "").trim();
  const now = new Date();

  let found = false;
  entries.forEach(entry => {
    if (!entry) return;
    const entryStep = entry.step || entry.to;
    if (entryStep !== step) return;
    if (who && entry.assignee && String(entry.assignee).toUpperCase().trim() !== who.toUpperCase()) return;
    entry.status = status;
    entry.timestamp = now.getTime();
    entry.dateStr = now.toLocaleString();
    if (who && !entry.assignee) entry.assignee = who;
    found = true;
  });

  if (!found) {
    entries.push({
      step: step,
      status: status,
      assignee: who,
      timestamp: now.getTime(),
      dateStr: now.toLocaleString()
    });
  }
  return entries;
}

/** Lee una fila completa (objeto por encabezado) buscando por FOLIO/ID. */
function internalFindRowObject(sheetName, folio) {
  try {
    const sheet = findSheetSmart(sheetName);
    if (!sheet) return null;
    const values = sheet.getDataRange().getValues();
    const headerRowIndex = findHeaderRow(values);
    if (headerRowIndex === -1) return null;
    const headers = values[headerRowIndex].map(h => String(h).toUpperCase().replace(/\n/g, " ").replace(/\s+/g, " ").trim());
    let folioIdx = headers.indexOf("FOLIO");
    if (folioIdx === -1) folioIdx = headers.indexOf("ID");
    if (folioIdx === -1) return null;
    const target = String(folio).toUpperCase().trim();
    for (let i = headerRowIndex + 1; i < values.length; i++) {
      if (String(values[i][folioIdx]).toUpperCase().trim() === target) {
        const obj = {};
        headers.forEach((h, j) => { if (h) obj[h] = values[i][j]; });
        obj._rowIndex = i + 1;
        return obj;
      }
    }
    return null;
  } catch (e) {
    console.warn("internalFindRowObject: " + e.toString());
    return null;
  }
}

/** Hoja destino de un trabajador: tracker personal y, si no existe, su tabla (VENTAS). */
function resolveWorkerSheet(workerName) {
  const clean = String(workerName || "").replace(/\s*\(VENTAS\)/ig, "").trim();
  if (!clean) return null;
  if (findSheetSmart(clean)) return clean;
  if (findSheetSmart(clean + " (VENTAS)")) return clean + " (VENTAS)";
  return null;
}

/**
 * DISTRIBUCIÓN LATERAL ("PAPA CALIENTE")
 * Detecta una delegación de fase dentro del payload y:
 *   1. Actualiza PROCESO_LOG y MAP COT sobre el propio taskData (para que se
 *      escriba en la hoja maestra en el mismo guardado).
 *   2. Crea la fila delegada en la hoja de cada trabajador, marcando el
 *      CONCEPTO con la fase, ej: "COTIZACION PLANTA [Calculo y Diseño]".
 * Soporta el contrato del frontend (`_assignToWorker` + `_assignStep`) y el
 * genérico (`PROCESO`/`ETAPA` + `INVOLUCRADOS`).
 * @returns {{step: string, workers: Array<string>, targets: Array<string>}|null}
 */
function internalApplyHotPotato(sheetName, taskData, username, useOwnLock = true) {
  try {
    if (!taskData) return null;

    // 1. Trabajadores destino
    let workers = [];
    if (taskData._assignToWorker) {
      workers = Array.isArray(taskData._assignToWorker) ? taskData._assignToWorker.slice() : [taskData._assignToWorker];
    }
    if (workers.length === 0) {
      const involucrados = pickTaskValue(taskData, ["INVOLUCRADOS", "RESPONSABLE", "ASIGNADO"]);
      if (involucrados) workers = String(involucrados).split(",");
    }
    workers = workers.map(w => String(w || "").trim()).filter(w => w && normalizeStaffName(w) !== normalizeStaffName(sheetName));
    if (workers.length === 0) return null;

    // 2. Fase delegada
    const step = normalizePhaseId(
      taskData._assignStep ||
      pickTaskValue(taskData, ["PROCESO", "ETAPA", "FASE", "MAP COT"])
    );
    if (!step) return null;

    const folio = String(pickTaskValue(taskData, ["FOLIO", "ID"]) || "").trim();
    if (!folio) return null;

    // 3. Datos maestros de la cotización
    const master = internalFindRowObject(sheetName, folio) || {};
    const conceptoBase = stripPhaseMarker(pickTaskValue(taskData, ["CONCEPTO", "DESCRIPCION"]) || master["CONCEPTO"] || master["DESCRIPCION"] || "");
    const cliente = pickTaskValue(taskData, ["CLIENTE"]) || master["CLIENTE"] || "";
    const clasificacion = pickTaskValue(taskData, ["CLASIFICACION", "CLASI"]) || master["CLASIFICACION"] || "";
    const fechaMaestra = pickTaskValue(taskData, ["FECHA", "FECHA ALTA", "ALTA"]) || master["FECHA"] || new Date();

    // 4. PROCESO_LOG + MAP COT sobre la hoja maestra
    let log = parseProcesoLog(pickTaskValue(taskData, ["PROCESO_LOG"]) || master["PROCESO_LOG"]);
    workers.forEach(w => { log = upsertProcesoLogEntry(log, step, w, "IN_PROGRESS"); });
    taskData["PROCESO_LOG"] = JSON.stringify(log);
    taskData["MAP COT"] = buildMapCot(log, step);

    // 5. Filas delegadas
    const targets = [];
    workers.forEach(worker => {
      const targetSheet = resolveWorkerSheet(worker);
      if (!targetSheet) {
        registrarLog(username || "SISTEMA", "PAPA_CALIENTE_SKIP", "Sin hoja para " + worker + " (folio " + folio + ")");
        return;
      }
      const delegated = {
        FOLIO: folio,
        CLIENTE: cliente,
        CONCEPTO: conceptoBase + " [" + phaseLabel(step) + "]",
        FECHA: fechaMaestra,
        ESTATUS: "ASIGNADO",
        AVANCE: "",
        CLASIFICACION: clasificacion,
        RESPONSABLE: worker,
        VENDEDOR: worker,
        COMENTARIOS: "Fase delegada desde " + sheetName + " por " + (username || "SISTEMA")
      };
      const res = internalBatchUpdateTasks(targetSheet, [delegated], useOwnLock);
      if (res && res.success) {
        targets.push(targetSheet);
      } else {
        registrarLog(username || "SISTEMA", "PAPA_CALIENTE_FAIL", targetSheet + ": " + (res && res.message));
      }
    });

    registrarLog(username || "SISTEMA", "PAPA_CALIENTE",
      "Folio " + folio + " fase " + step + " -> " + workers.join(", "));
    return { step: step, workers: workers, targets: targets };
  } catch (e) {
    console.error("internalApplyHotPotato: " + e.toString());
    return null;
  }
}

/**
 * REVERSE SYNC (trabajador -> ANTONIA_VENTAS)
 * Replica en la hoja maestra los avances del trabajador PERO:
 *   - Borra ESTATUS/AVANCE/CUMPLIMIENTO (comparación case-insensitive) para
 *     que una fase parcial no cierre la venta global (AGENTS.md §3).
 *   - No pisa el CONCEPTO maestro con el concepto marcado de la fase.
 *   - Marca la fase como DONE en PROCESO_LOG y pinta MAP COT en verde.
 */
function internalReverseSyncToAntonia(sourceSheetName, tasks, username, useOwnLock = true) {
  const blockedKeys = ["ESTATUS", "STATUS", "AVANCE", "AVANCE %", "% AVANCE", "CUMPLIMIENTO", "FECHA_TERMINO", "FECHA TERMINO"];
  const master = SALES_ROUTING_CONFIG.masterSalesSheet;
  const results = [];

  (tasks || []).forEach(task => {
    try {
      const folio = String(pickTaskValue(task, ["FOLIO", "ID"]) || "").trim();
      if (!folio) return;

      // 1. Payload saneado
      const clean = {};
      Object.keys(task).forEach(key => {
        if (key.startsWith("_")) return;
        const up = String(key).toUpperCase().replace(/\n/g, " ").replace(/\s+/g, " ").trim();
        if (blockedKeys.indexOf(up) > -1) return;                       // cierre prematuro
        if (up === "CONCEPTO" && /\[[^\]]+\]/.test(String(task[key]))) return; // concepto marcado
        clean[key] = task[key];
      });
      clean["FOLIO"] = folio;

      // 2. Estado real de la fila del trabajador
      const workerRow = internalFindRowObject(sourceSheetName, folio) || {};
      const phase = extractPhaseFromConcepto(workerRow["CONCEPTO"] || pickTaskValue(task, ["CONCEPTO"]));
      const completed = isProgressComplete(workerRow["AVANCE"] !== undefined ? workerRow["AVANCE"] : pickTaskValue(task, ["AVANCE"]))
        || isTerminalStatus(workerRow["ESTATUS"] !== undefined ? workerRow["ESTATUS"] : pickTaskValue(task, ["ESTATUS"]));

      // 3. Timeline de la maestra
      if (phase) {
        const masterRow = internalFindRowObject(master, folio) || {};
        const log = upsertProcesoLogEntry(
          masterRow["PROCESO_LOG"],
          phase,
          normalizeStaffName(sourceSheetName),
          completed ? "DONE" : "IN_PROGRESS"
        );
        clean["PROCESO_LOG"] = JSON.stringify(log);
        clean["MAP COT"] = buildMapCot(log, phase);
      }

      const res = internalBatchUpdateTasks(master, [clean], useOwnLock, { skipNotify: true });
      results.push({ folio: folio, phase: phase, completed: completed, success: !!(res && res.success) });
      if (res && res.success) {
        registrarLog(username || "SISTEMA", "REVERSE_SYNC",
          "Folio " + folio + (phase ? (" fase " + phase + (completed ? " DONE" : " EN CURSO")) : "") + " desde " + sourceSheetName);
      }
    } catch (e) {
      console.error("internalReverseSyncToAntonia: " + e.toString());
    }
  });
  return results;
}

// ----------------------------------------------------------------------
// D-bis. SUPABASE SYNC (ESCRITURA DOBLE SHEETS -> POSTGRES)
// ----------------------------------------------------------------------
/**
 * Replica en Supabase cada escritura que la app hace en Sheets.
 *
 * Es el puente de la migración: mientras exista, Sheets sigue siendo la fuente
 * de verdad y Supabase deja de ser una copia estática que se desactualiza.
 * Ver docs/PLAN_BACKEND_PYTHON.md (Fase 0.5).
 *
 * INVARIANTE: este módulo NUNCA puede romper un guardado. Todo va envuelto en
 * try/catch y `muteHttpExceptions`; si Supabase está caído, lento o mal
 * configurado, la escritura en Sheets ya ocurrió y la operación continúa. Se
 * comporta igual que NotifierService: mejor perder una réplica que una tarea.
 *
 * Configuración por Propiedades del Script (nunca en el fuente):
 *   SUPABASE_URL           https://<proyecto>.supabase.co
 *   SUPABASE_KEY           clave de servicio (service_role)
 *   SUPABASE_SYNC_ENABLED  "false" para desactivar sin borrar credenciales
 */
const SUPABASE_CONFIG = {
  urlProperty: "SUPABASE_URL",
  keyProperty: "SUPABASE_KEY",
  enabledProperty: "SUPABASE_SYNC_ENABLED",
  timeoutMs: 15000,

  // Folios con secuencia global: son únicos en todo el sistema.
  globalFolioPrefixes: ["PPC-", "AV-", "TG-", "WO-", "SITE-", "PROJ-"],

  // IDs tipo timestamp. El sufijo ".0" opcional es real: Google Sheets entrega
  // los folios numéricos como número y al serializarlos aparece "1772639658256.0".
  timestampFolioRegex: /^\d{10,}(?:\.0+)?$/
};

// --- ESTATUS CANÓNICOS (espejo de api/services/tracker_rules.py) ---
// Los alias van escritos uno a uno a propósito: una coincidencia difusa
// adivinaría, y aquí un error cambia si una tarea se archiva o no.
// Cada alias apunta a un canónico de SU MISMA familia, de modo que
// isTerminalStatus() da el mismo resultado antes y después de normalizar.
const CANONICAL_STATUSES = {
  "ASIGNADO": ["ASIGNADA", "ASIGANDO", "ASIGANDA", "ASIGADO", "ASIGANDOA",
               "ASIGANADO", "ASIGANADA", "ASIGNDO", "ASIGNADOO", "ASIGNAD",
               "ASIGNSDO", "ASIGNBADO", "ASIGNADP"],
  "PENDIENTE": ["PEDIENTE", "PENDIENT", "PENDINTE", "PEDIENTES", "PENDIENTES"],
  "PENDIENTE VISITA": ["PENDIENTE DE VISITA", "PDTE VISITA", "PENDIENTE VISTA"],
  "PENDIENTE INFORMACION": ["PENDIENTE INFORMACION POR PLANTA",
                            "PENDIENTE DE INFORMACION", "PENDIENTE INFO"],
  "FALTA INFORMACION": ["FALTA INFO", "FALTA DE INFORMACION"],
  "EN REVISION": ["REVISION", "EN REVISON", "EN REVICION"],
  "EN PROCESO": ["PROCESO", "EN PROSESO"],
  "ENVIADA": ["ENVIADO", "ENVIDA"],
  "ABIERTO": ["ABIERTA", "BIERTO", "BIERTA"],
  "SUSPENDIDA": ["SUSPENDIDO", "SUSPENDIA"],
  "PERDIDA POR TIEMPO": ["PERDIDA X TIEMPO", "PERDIDA TIEMPO",
                         "PERDIDO POR TIEMPO", "PERDIDO X TIEMPO"],
  "CANCELADA": ["CANCELADO", "CANCELADA X PLANTA", "CANCELADA POR PLANTA",
                "CANCELADA X CLIENTE", "CANCELADA POR CLIENTE"],
  // Terminales: se conservan tal cual para no alterar el auto-archivado.
  "HECHO": [], "TERMINADO": [], "FINALIZADO": [], "REALIZADO": [],
  "COMPLETADO": [], "DONE": [], "CERRADO": [],
  "GANADA": ["GANADO"], "PERDIDA": ["PERDIDO"]
};

const STATUS_PLACEHOLDERS = ["", "-", "--", "---", "N/A", "NA", "NULL",
                             "NINGUNO", ".", "..", "...", "#N/A",
                             "ESTATUS", "STATUS"];

const STATUS_LOOKUP = (function () {
  const mapa = {};
  const clave = function (s) {
    let t = String(s);
    if (t.normalize) t = t.normalize("NFD").replace(/[̀-ͯ]/g, "");
    return t.replace(/[.,;:_/\\-]+/g, " ").replace(/\s+/g, " ").trim().toUpperCase();
  };
  Object.keys(CANONICAL_STATUSES).forEach(function (canon) {
    mapa[clave(canon)] = canon;
    CANONICAL_STATUSES[canon].forEach(function (a) { mapa[clave(a)] = canon; });
  });
  return mapa;
})();

const SupabaseSync = {

  // --- Configuración -------------------------------------------------

  _props: function () {
    try { return PropertiesService.getScriptProperties(); } catch (e) { return null; }
  },

  getConfig: function () {
    const props = this._props();
    if (!props) return null;
    const url = String(props.getProperty(SUPABASE_CONFIG.urlProperty) || "").trim().replace(/\/+$/, "");
    const key = String(props.getProperty(SUPABASE_CONFIG.keyProperty) || "").trim();
    if (!url || !key) return null;
    const enabled = String(props.getProperty(SUPABASE_CONFIG.enabledProperty) || "true").trim().toLowerCase();
    if (enabled === "false" || enabled === "0" || enabled === "no") return null;
    return { url: url, key: key };
  },

  isEnabled: function () { return this.getConfig() !== null; },

  // --- Reglas de negocio ---------------------------------------------

  /**
   * Clave de identidad de fila en `tasks`. Verificada con paridad exacta
   * contra los 4,626 registros ya migrados.
   *
   * Orden de evaluación (importa):
   *   1. El folio ya trae "::"  -> es sintético ("HOJA::ROW123"), se usa tal cual.
   *   2. Prefijo de secuencia global (PPC-, AV-, TG-, ...) -> único global.
   *   3. ID tipo timestamp (10+ dígitos) -> único global.
   *   4. Cualquier otro -> "<hoja>::<folio>", único solo dentro de su hoja.
   *
   * OJO: los folios con iniciales de persona (JO-0009, SP-0007, GM-0123) caen
   * en el caso 4, NO en el 2. Un mismo JO-0009 vive en 10 trackers distintos
   * (difusión "papa caliente") y cada copia necesita su propia clave.
   */
  computeDedupeKey: function (folio, sheetName) {
    const f = String(folio === null || folio === undefined ? "" : folio).trim();
    if (!f) return null;
    if (f.indexOf("::") >= 0) return f;
    const up = f.toUpperCase();
    for (let i = 0; i < SUPABASE_CONFIG.globalFolioPrefixes.length; i++) {
      if (up.indexOf(SUPABASE_CONFIG.globalFolioPrefixes[i]) === 0) return f;
    }
    if (SUPABASE_CONFIG.timestampFolioRegex.test(f)) return f;
    // OJO: el nombre de la hoja va SIN trim, a propósito. Varias hojas reales
    // tienen un espacio inicial (" LILIANA AYLIN MARTINEZ IBARRA") y la
    // migración lo conservó dentro de la clave. Normalizarlo aquí generaría
    // una clave distinta a la ya almacenada y el upsert insertaría un
    // duplicado en vez de actualizar la fila existente.
    return String(sheetName === null || sheetName === undefined ? "" : sheetName) + "::" + f;
  },

  /**
   * AVANCE a escala 0-100 (AGENTS.md §4).
   *
   * El número nativo 1 viene de una celda con formato porcentual y significa
   * 100 %. El string "1" lo tecleó una persona y significa 1 %. Colapsar
   * ambos casos archivaría como terminadas las tareas al 1 %.
   */
  normalizeAvance: function (value) {
    if (value === null || value === undefined || value === "") return null;
    if (typeof value === "boolean") return null;
    if (value instanceof Date) return null;

    if (typeof value === "number") {
      if (!isFinite(value)) return null;
      // Celda con formato porcentual: 1 = 100 %, 0.5 = 50 %.
      const n = (value > 0 && value <= 1) ? value * 100 : value;
      return Math.round(n * 100) / 100;
    }

    const raw = String(value).trim();
    if (!raw) return null;
    const num = parseFloat(raw.replace("%", "").replace(",", ".").trim());
    if (isNaN(num)) return null;
    // Texto: se toma tal cual, ya está en escala 0-100.
    return Math.round(num * 100) / 100;
  },

  /**
   * Estatus canónico para escribir en la base.
   *
   * La columna venía de captura libre y acumuló 45 valores distintos en
   * `tasks` para lo que son ~11 estatus: mayúsculas, acentos, género
   * (ASIGNADO/ASIGNADA) y erratas (ASIGANDO, PEDIENTE, BIERTO). Se limpió una
   * vez con scripts/normalizar_estatus.py; esto evita que se vuelva a ensuciar.
   *
   * Un valor no reconocido se conserva tal cual (solo recortado). Descartarlo
   * sería peor: si mañana el equipo empieza a usar un estatus nuevo, tirarlo
   * en silencio perdería el dato. Aparecerá en la próxima revisión.
   */
  normalizeStatus: function (value) {
    if (value === null || value === undefined) return "";
    var crudo = String(value).replace(/[\n\r]+/g, " ").trim();
    if (!crudo) return "";

    // Clave: mayúsculas, sin acentos, sin puntuación de relleno.
    var clave = crudo.normalize ? crudo.normalize("NFD").replace(/[̀-ͯ]/g, "") : crudo;
    clave = clave.replace(/[.,;:_/\\-]+/g, " ").replace(/\s+/g, " ").trim().toUpperCase();

    if (!clave || STATUS_PLACEHOLDERS.indexOf(clave) >= 0) return "";
    if (STATUS_LOOKUP[clave]) return STATUS_LOOKUP[clave];

    // Familias con sufijo libre ("PERDIDA X TIEMPO DEL CLIENTE").
    if ((clave.indexOf("PERDIDA ") === 0 || clave.indexOf("PERDIDO ") === 0) &&
        clave.indexOf("TIEMPO") >= 0) return "PERDIDA POR TIEMPO";
    if (clave.indexOf("CANCELAD") === 0) return "CANCELADA";
    if (clave.indexOf("SUSPENDID") === 0) return "SUSPENDIDA";

    return crudo;   // desconocido: se conserva
  },

  /** Fecha -> "YYYY-MM-DD" (columnas `date`). Devuelve null si no es fecha. */
  toIsoDate: function (value) {
    if (value === null || value === undefined || value === "") return null;
    let d = null;
    if (value instanceof Date) {
      d = value;
    } else {
      const raw = String(value).trim();
      if (!raw) return null;
      // dd/MM/yy y dd/MM/yyyy, el formato que teclea el equipo.
      const m = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
      if (m) {
        let anio = parseInt(m[3], 10);
        if (anio < 100) anio += 2000;
        d = new Date(anio, parseInt(m[2], 10) - 1, parseInt(m[1], 10));
      } else {
        const parsed = new Date(raw);
        if (!isNaN(parsed.getTime())) d = parsed;
      }
    }
    if (!d || isNaN(d.getTime())) return null;
    const mes = ("0" + (d.getMonth() + 1)).slice(-2);
    const dia = ("0" + d.getDate()).slice(-2);
    return d.getFullYear() + "-" + mes + "-" + dia;
  },

  /**
   * Nombre de hoja tal cual, sin recortar. Los datos ya migrados conservan
   * los espacios del nombre real (hay hojas con espacio inicial), así que
   * normalizarlo aquí reescribiría `source_sheet` en cada upsert.
   */
  _sheetTag: function (sheetName) {
    if (sheetName === null || sheetName === undefined) return null;
    const s = String(sheetName);
    return s === "" ? null : s;
  },

  /** Texto plano, o null si viene vacío (evita ensuciar con cadenas ""). */
  _texto: function (value) {
    if (value === null || value === undefined) return null;
    if (value instanceof Date) return this.toIsoDate(value);
    const s = String(value).trim();
    return s ? s : null;
  },

  // --- Transporte -----------------------------------------------------

  /**
   * Llamada a PostgREST. Nunca lanza: devuelve {success, code, body}.
   */
  _request: function (metodo, ruta, payload, preferencias) {
    const cfg = this.getConfig();
    if (!cfg) return { success: false, message: "Supabase no configurado" };
    try {
      const opciones = {
        method: metodo,
        contentType: "application/json",
        muteHttpExceptions: true,
        headers: {
          apikey: cfg.key,
          Authorization: "Bearer " + cfg.key,
          Prefer: preferencias || "return=minimal"
        }
      };
      if (payload !== null && payload !== undefined) {
        opciones.payload = JSON.stringify(payload);
      }
      const respuesta = UrlFetchApp.fetch(cfg.url + "/rest/v1/" + ruta, opciones);
      const code = respuesta.getResponseCode();
      const ok = code >= 200 && code < 300;
      if (!ok) {
        console.warn("[SupabaseSync] " + metodo + " " + ruta + " -> " + code + ": " +
                     String(respuesta.getContentText()).slice(0, 300));
      }
      return { success: ok, code: code, body: respuesta.getContentText() };
    } catch (e) {
      console.warn("[SupabaseSync] Fallo de red en " + ruta + ": " + e.toString());
      return { success: false, message: e.toString() };
    }
  },

  // --- Directorio (para resolver assignee_id) --------------------------

  /** Mapa NOMBRE -> people.id, cacheado 10 min para no consultar por fila. */
  _peopleMap: function () {
    let cache = null;
    try { cache = CacheService.getScriptCache(); } catch (e) { cache = null; }
    if (cache) {
      const guardado = cache.get("SB_PEOPLE_MAP");
      if (guardado) { try { return JSON.parse(guardado); } catch (e) {} }
    }
    const res = this._request("GET", "people?select=id,nombre", null, "count=none");
    if (!res.success) return {};
    let filas = [];
    try { filas = JSON.parse(res.body) || []; } catch (e) { return {}; }
    const mapa = {};
    filas.forEach(function (p) {
      const n = String(p.nombre || "").toUpperCase().trim();
      if (n && !mapa[n]) mapa[n] = p.id;
    });
    if (cache) { try { cache.put("SB_PEOPLE_MAP", JSON.stringify(mapa), 600); } catch (e) {} }
    return mapa;
  },

  /**
   * Resuelve el id de una persona. Si el valor trae varios nombres separados
   * por coma o salto de línea (columna INVOLUCRADOS), toma el primero: nunca
   * se debe crear una persona llamada "RAMIRO RODRIGUEZ, ALFONSO CORREA".
   */
  _resolvePersonId: function (nombreCrudo, mapa) {
    const crudo = String(nombreCrudo || "").trim();
    if (!crudo) return null;
    const primero = crudo.split(/[,\n;]/)[0];
    const limpio = normalizeStaffName(String(primero).replace(SALES_ROUTING_CONFIG.salesSuffixRegex, ""));
    if (!limpio) return null;
    return mapa[limpio] || null;
  },

  // --- Espejo de tareas ------------------------------------------------

  /** Objeto de tarea (forma de hoja) -> fila de `tasks`. */
  buildTaskRow: function (task, sheetName, peopleMap) {
    const folio = pickTaskValue(task, ["FOLIO", "ID"]);
    const dedupeKey = this.computeDedupeKey(folio, sheetName);
    if (!dedupeKey) return null;

    const responsable = pickTaskValue(task, ["RESPONSABLE", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO"]);
    const fila = {
      dedupe_key: dedupeKey,
      folio: this._texto(folio),
      // Sin trim, por lo mismo que computeDedupeKey: el valor ya migrado
      // conserva los espacios del nombre real de la hoja.
      source_sheet: this._sheetTag(sheetName),
      assignee_raw: this._texto(responsable),
      departamento: this._texto(pickTaskValue(task, ["AREA", "ESPECIALIDAD", "DEPARTAMENTO", "ALTA"])),
      fecha_alta: this.toIsoDate(pickTaskValue(task, ["FECHA", "FECHA ALTA", "ALTA", "FECHA DE ALTA"])),
      clasificacion: this._texto(pickTaskValue(task, ["CLASIFICACION", "CLASI"])),
      concepto: this._texto(pickTaskValue(task, ["CONCEPTO", "DESCRIPCION", "ACTIVIDAD"])),
      avance: this.normalizeAvance(pickTaskValue(task, ["AVANCE", "AVANCE %", "% AVANCE"])),
      fecha_estimada_fin: this.toIsoDate(pickTaskValue(task, ["FECHA ESTIMADA DE FIN", "FECHA ESTIMADA", "FECHA_FIN", "FECHA FIN"])),
      reloj: this._texto(pickTaskValue(task, ["RELOJ"])),
      restricciones: this._texto(pickTaskValue(task, ["RESTRICCIONES", "RESTRICCION"])),
      prioridad: this._texto(pickTaskValue(task, ["PRIORIDAD", "PRIORIDADES"])),
      riesgos: this._texto(pickTaskValue(task, ["RIESGOS", "RIESGO"])),
      fecha_respuesta: this.toIsoDate(pickTaskValue(task, ["FECHA_RESPUESTA", "FECHA RESPUESTA", "DEADLINE"])),
      carpeta: this._texto(pickTaskValue(task, ["ARCHIVO", "CARPETA", "LINK", "URL", "EVIDENCIA"])),
      cumplimiento: this._texto(pickTaskValue(task, ["CUMPLIMIENTO", "CUMPL.", "CUMP"])),
      comentarios: this._texto(pickTaskValue(task, ["COMENTARIOS", "COMENTARIO", "OBSERVACIONES", "NOTAS"])),
      comentarios_semana: this._texto(pickTaskValue(task, ["COMENTARIOS SEMANA EN CURSO"])),
      comentarios_semana_previa: this._texto(pickTaskValue(task, ["COMENTARIOS PREVIOS", "PREVIOS", "COMENTARIOS SEMANA PREVIA"])),
      // Estatus canonico: evita que la columna vuelva a acumular 45 variantes.
      status: this.normalizeStatus(pickTaskValue(task, ["ESTATUS", "STATUS"]))
    };

    const personId = this._resolvePersonId(responsable, peopleMap);
    if (personId) fila.assignee_id = personId;

    // Solo se envían columnas con valor: en un upsert con merge, una columna
    // ausente conserva lo que ya había en la base en vez de borrarlo.
    const limpia = {};
    Object.keys(fila).forEach(function (k) {
      if (fila[k] !== null && fila[k] !== undefined) limpia[k] = fila[k];
    });
    limpia.dedupe_key = dedupeKey;   // siempre presente: es la clave del upsert
    return limpia;
  },

  /** Objeto de cotización -> fila de `quotes` (PK: folio). */
  buildQuoteRow: function (task, sheetName, peopleMap) {
    const folio = pickTaskValue(task, ["FOLIO", "ID"]);
    const f = this._texto(folio);
    if (!f) return null;

    const vendedor = pickTaskValue(task, ["VENDEDOR", "RESPONSABLE", "INVOLUCRADOS"]);
    const fila = {
      folio: f,
      source_sheet: this._sheetTag(sheetName),
      vendedor_raw: this._texto(vendedor),
      cliente: this._texto(pickTaskValue(task, ["CLIENTE"])),
      area: this._texto(pickTaskValue(task, ["AREA", "ESPECIALIDAD", "DEPARTAMENTO"])),
      clasificacion: this._texto(pickTaskValue(task, ["CLASIFICACION", "CLASI"])),
      concepto: this._texto(pickTaskValue(task, ["CONCEPTO", "DESCRIPCION"])),
      f_visita: this.toIsoDate(pickTaskValue(task, ["F_VISITA", "F. VISITA", "FECHA VISITA"])),
      f_inicio: this.toIsoDate(pickTaskValue(task, ["F_INICIO", "F. INICIO", "FECHA", "FECHA INICIO"])),
      f_entrega: this.toIsoDate(pickTaskValue(task, ["F_ENTREGA", "F. ENTREGA", "FECHA DE ENTREGA"])),
      avance: this.normalizeAvance(pickTaskValue(task, ["AVANCE", "AVANCE %", "% AVANCE"])),
      estatus: this.normalizeStatus(pickTaskValue(task, ["ESTATUS", "STATUS"])),
      comentarios: this._texto(pickTaskValue(task, ["COMENTARIOS", "COMENTARIO", "OBSERVACIONES"])),
      archivo: this._texto(pickTaskValue(task, ["ARCHIVO", "LINK", "URL"])),
      cotizacion: this._texto(pickTaskValue(task, ["COTIZACION", "COTIZACIÓN"])),
      // "TIMEOUT" es una errata real de "TIMELINE" en varias hojas.
      timeline: this._texto(pickTaskValue(task, ["TIMELINE", "TIMEOUT"])),
      layout: this._texto(pickTaskValue(task, ["LAYOUT"])),
      f2: this._texto(pickTaskValue(task, ["F2"])),
      proceso: this._texto(pickTaskValue(task, ["PROCESO"])),
      proceso_log: this._texto(pickTaskValue(task, ["PROCESO_LOG"])),
      map_cot: this._texto(pickTaskValue(task, ["MAP_COT"])),
      requisitor: this._texto(pickTaskValue(task, ["REQUISITOR"])),
      prioridad_cot: this._texto(pickTaskValue(task, ["PRIORIDAD", "PRIORIDAD_COT"])),
      reloj: this._texto(pickTaskValue(task, ["RELOJ"]))
    };

    const monto = parseFloat(String(pickTaskValue(task, ["MONTO"]) || "").replace(/[^0-9.\-]/g, ""));
    if (!isNaN(monto)) fila.monto = monto;

    const vendedorId = this._resolvePersonId(vendedor, peopleMap);
    if (vendedorId) fila.vendedor_id = vendedorId;

    const limpia = {};
    Object.keys(fila).forEach(function (k) {
      if (fila[k] !== null && fila[k] !== undefined) limpia[k] = fila[k];
    });
    limpia.folio = f;
    return limpia;
  },

  /**
   * Punto de entrada: replica un lote ya escrito en Sheets.
   * Se llama DESPUÉS del flush, igual que las notificaciones.
   */
  mirrorBatch: function (sheetName, tasks) {
    try {
      if (!this.isEnabled()) return { success: false, skipped: true };
      if (!tasks || !tasks.length) return { success: true, count: 0 };

      const esVentas = isSalesSheet(sheetName);
      const peopleMap = this._peopleMap();
      const self = this;
      const filas = [];
      tasks.forEach(function (t) {
        const fila = esVentas ? self.buildQuoteRow(t, sheetName, peopleMap)
                              : self.buildTaskRow(t, sheetName, peopleMap);
        if (fila) filas.push(fila);
      });
      if (!filas.length) return { success: true, count: 0 };

      const tabla = esVentas ? "quotes" : "tasks";
      const conflicto = esVentas ? "folio" : "dedupe_key";
      const res = this._request(
        "POST", tabla + "?on_conflict=" + conflicto, filas,
        "resolution=merge-duplicates,return=minimal"
      );
      return { success: res.success, count: filas.length, table: tabla };
    } catch (e) {
      console.warn("[SupabaseSync] mirrorBatch falló: " + e.toString());
      return { success: false, message: e.toString() };
    }
  },

  /** Espejo de registrarLog() en la tabla `system_log`. */
  mirrorLog: function (usuario, accion, detalles) {
    try {
      if (!this.isEnabled()) return { success: false, skipped: true };
      const fila = {
        fecha_hora: new Date().toISOString(),
        usuario: this._texto(usuario) || "DESCONOCIDO",
        accion: this._texto(accion),
        detalles: this._texto(detalles)
      };
      const res = this._request("POST", "system_log", [fila], "return=minimal");
      return { success: res.success };
    } catch (e) {
      console.warn("[SupabaseSync] mirrorLog falló: " + e.toString());
      return { success: false, message: e.toString() };
    }
  }
};

// ----------------------------------------------------------------------
// E. NOTIFIER SERVICE (MAKE.COM -> OUTLOOK)
// ----------------------------------------------------------------------

const NotifierService = {
  /** URL del webhook (configurable en Propiedades del Script). */
  getWebhookUrl: function () {
    try {
      const props = PropertiesService.getScriptProperties();
      const custom = props.getProperty(NOTIFIER_CONFIG.urlProperty);
      return (custom && custom.trim()) ? custom.trim() : NOTIFIER_CONFIG.defaultUrl;
    } catch (e) {
      return NOTIFIER_CONFIG.defaultUrl;
    }
  },

  isEnabled: function () {
    try {
      const flag = PropertiesService.getScriptProperties().getProperty(NOTIFIER_CONFIG.enabledProperty);
      if (flag !== null && String(flag).toUpperCase() === "FALSE") return false;
    } catch (e) { /* por defecto habilitado */ }
    return !!this.getWebhookUrl();
  },

  /**
   * Payload para Make.com. La fecha SIEMPRE viaja como .toISOString()
   * (con milisegundos y "Z") para que Outlook conserve la zona horaria.
   */
  buildPayload: function (sheetName, task, assignee) {
    const fecha = parseSheetDate(pickTaskValue(task, ["FECHA", "FECHA ALTA", "ALTA", "FECHA INICIO"])) || new Date();
    const fechaFin = parseSheetDate(pickTaskValue(task, ["FECHA_RESPUESTA", "FECHA RESPUESTA", "FECHA FIN"]));
    return {
      evento: "TAREA_ASIGNADA",
      hoja: sheetName,
      origen: isSalesSheet(sheetName) ? "tabla de ventas" : "tracker general",
      esVenta: isSalesSheet(sheetName),
      folio: String(pickTaskValue(task, ["FOLIO", "ID"]) || ""),
      concepto: String(pickTaskValue(task, ["CONCEPTO", "DESCRIPCION"]) || ""),
      responsable: assignee,
      email: resolveUserEmail(assignee),
      cliente: String(pickTaskValue(task, ["CLIENTE"]) || ""),
      clasificacion: String(pickTaskValue(task, ["CLASIFICACION", "CLASI"]) || ""),
      estatus: String(pickTaskValue(task, ["ESTATUS", "STATUS"]) || "ASIGNADO"),
      fechaInicio: fecha.toISOString(),
      fechaFin: fechaFin ? fechaFin.toISOString() : "",
      enviadoEn: new Date().toISOString()
    };
  },

  /** Envía el payload al webhook. Nunca lanza: un fallo no debe romper el guardado. */
  sendToOutlook: function (payload) {
    try {
      if (!this.isEnabled()) return { success: false, message: "Webhook deshabilitado" };
      if (!payload || !payload.email) return { success: false, message: "Responsable sin correo corporativo" };
      const response = UrlFetchApp.fetch(this.getWebhookUrl(), {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify(payload),
        muteHttpExceptions: true
      });
      const code = response.getResponseCode ? response.getResponseCode() : 200;
      return { success: code >= 200 && code < 300, code: code };
    } catch (e) {
      console.warn("NotifierService.sendToOutlook: " + e.toString());
      return { success: false, message: e.toString() };
    }
  },

  /** Notifica la asignación de una tarea nueva a su responsable. */
  notifyAssignment: function (sheetName, task) {
    try {
      const assignee = String(
        pickTaskValue(task, ["RESPONSABLE", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO"]) || sheetName
      ).split(",")[0].trim();
      if (!assignee) return { success: false, message: "Sin responsable" };
      const payload = this.buildPayload(sheetName, task, assignee);
      if (!payload.email) return { success: false, message: "Sin correo para " + assignee };
      return this.sendToOutlook(payload);
    } catch (e) {
      return { success: false, message: e.toString() };
    }
  }
};

/** Hojas que nunca disparan notificación (espejos y catálogos). */
function shouldNotifySheet(sheetName) {
  const up = String(sheetName || "").toUpperCase().trim();
  if (!up) return false;
  if (up.indexOf("DB_") === 0 || up.indexOf("LOG_") === 0) return false;
  if (up === "ADMINISTRADOR") return false;   // hoja espejo de control
  if (up === APP_CONFIG.ppcSheetName.toUpperCase() || up === "PPCV4") return false;
  if (up === APP_CONFIG.draftSheetName.toUpperCase()) return false;
  return true;
}

// ----------------------------------------------------------------------
// F. AGENTE DE MÉTRICAS DE COTIZACIONES
// ----------------------------------------------------------------------

/** Lee ANTONIA_VENTAS (activas + TAREAS REALIZADAS) y calcula los KPIs. */
function internalCollectQuoteMetrics(params) {
  const opts = params || {};
  const month = opts.month ? parseInt(opts.month, 10) : null;
  const year = opts.year ? parseInt(opts.year, 10) : null;

  const res = internalFetchSheetData(SALES_ROUTING_CONFIG.masterSalesSheet);
  if (!res.success) throw new Error(res.message || "No se pudo leer " + SALES_ROUTING_CONFIG.masterSalesSheet);

  // El historial (TAREAS REALIZADAS) es imprescindible: ahí viven las cerradas.
  const rows = (res.data || []).concat(res.history || []);

  const metrics = {
    totalCount: 0,
    month: month || (new Date().getMonth() + 1),
    year: year || new Date().getFullYear(),
    winLoss: { ganada: 0, perdida: 0, enProceso: 0, total: 0 },
    closeRate: 0,
    slaSummary: {
      A: { slaLimit: METRICS_CONFIG.slaLimits.A, count: 0, ok: 0, fail: 0, avgDays: 0, pctOk: 0 },
      AA: { slaLimit: METRICS_CONFIG.slaLimits.AA, count: 0, ok: 0, fail: 0, avgDays: 0, pctOk: 0 },
      AAA: { slaLimit: METRICS_CONFIG.slaLimits.AAA, count: 0, ok: 0, fail: 0, avgDays: 0, pctOk: 0 }
    },
    byCotizadorArr: [],
    byDepartmentArr: [],
    aaaByClientArr: [],
    alerts: []
  };

  const byCotizador = {};
  const byDepartment = {};
  const aaaByClient = {};
  const slaDays = { A: [], AA: [], AAA: [] };
  const hoy = new Date();

  rows.forEach(row => {
    const get = (keys) => pickTaskValue(row, keys);
    const fecha = parseSheetDate(get(["FECHA", "FECHA INICIO", "FECHA ALTA", "ALTA"]));
    if (month && year) {
      if (!fecha) return;
      if ((fecha.getMonth() + 1) !== month || fecha.getFullYear() !== year) return;
    }

    metrics.totalCount++;
    const estatus = String(get(["ESTATUS", "STATUS"]) || "");
    const bucket = classifyQuoteStatus(estatus);
    if (bucket === "GANADA") metrics.winLoss.ganada++;
    else if (bucket === "PERDIDA") metrics.winLoss.perdida++;
    else metrics.winLoss.enProceso++;
    metrics.winLoss.total++;

    const vendedor = String(get(["VENDEDOR", "RESPONSABLE", "COTIZADOR"]) || "SIN ASIGNAR").toUpperCase().trim();
    if (!byCotizador[vendedor]) byCotizador[vendedor] = { nombre: vendedor, total: 0, ganada: 0, perdida: 0, enProceso: 0 };
    byCotizador[vendedor].total++;
    if (bucket === "GANADA") byCotizador[vendedor].ganada++;
    else if (bucket === "PERDIDA") byCotizador[vendedor].perdida++;
    else byCotizador[vendedor].enProceso++;

    const depto = String(get(["AREA", "DEPARTAMENTO", "ESPECIALIDAD"]) || "GENERAL").toUpperCase().trim();
    if (!byDepartment[depto]) byDepartment[depto] = { nombre: depto, total: 0, ganada: 0, perdida: 0 };
    byDepartment[depto].total++;
    if (bucket === "GANADA") byDepartment[depto].ganada++;
    if (bucket === "PERDIDA") byDepartment[depto].perdida++;

    // SLA por clasificación
    const clase = String(get(["CLASIFICACION", "CLASI"]) || "").toUpperCase().trim();
    if (metrics.slaSummary[clase] && fecha) {
      const cierre = parseSheetDate(get(["FECHA_TERMINO", "FECHA TERMINO", "FECHA REAL"]));
      const referencia = cierre || hoy;
      const dias = Math.floor((referencia.getTime() - fecha.getTime()) / 86400000);
      const limite = metrics.slaSummary[clase].slaLimit;
      metrics.slaSummary[clase].count++;
      slaDays[clase].push(dias);
      if (dias <= limite) {
        metrics.slaSummary[clase].ok++;
      } else {
        metrics.slaSummary[clase].fail++;
        metrics.alerts.push({
          folio: String(get(["FOLIO", "ID"]) || ""),
          cliente: String(get(["CLIENTE"]) || ""),
          vendedor: vendedor,
          clasificacion: clase,
          dias: dias,
          slaLimit: limite,
          estatus: estatus
        });
      }
      if (clase === "AAA") {
        const cli = String(get(["CLIENTE"]) || "SIN CLIENTE").toUpperCase().trim();
        if (!aaaByClient[cli]) aaaByClient[cli] = { cliente: cli, total: 0, fueraSla: 0 };
        aaaByClient[cli].total++;
        if (dias > limite) aaaByClient[cli].fueraSla++;
      }
    }
  });

  Object.keys(metrics.slaSummary).forEach(clase => {
    const s = metrics.slaSummary[clase];
    const dias = slaDays[clase];
    s.avgDays = dias.length ? Math.round((dias.reduce((a, b) => a + b, 0) / dias.length) * 10) / 10 : 0;
    s.pctOk = s.count ? Math.round((s.ok / s.count) * 1000) / 10 : 0;
  });

  const cerradas = metrics.winLoss.ganada + metrics.winLoss.perdida;
  metrics.closeRate = cerradas ? Math.round((metrics.winLoss.ganada / cerradas) * 1000) / 10 : 0;

  metrics.byCotizadorArr = Object.keys(byCotizador).map(k => byCotizador[k]).sort((a, b) => b.total - a.total);
  metrics.byDepartmentArr = Object.keys(byDepartment).map(k => byDepartment[k]).sort((a, b) => b.total - a.total);
  metrics.aaaByClientArr = Object.keys(aaaByClient).map(k => aaaByClient[k]).sort((a, b) => b.total - a.total);

  return metrics;
}

/** API para el dashboard: métricas por reglas (sin IA). */
function apiFetchQuoteAgentMetrics(params) {
  try {
    return { success: true, metrics: internalCollectQuoteMetrics(params) };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/** Construye el prompt del analista de ventas para Gemini. */
function buildQuoteMetricsPrompt(metrics) {
  const sla = metrics.slaSummary;
  const topFallas = (metrics.alerts || []).slice(0, 15)
    .map(a => `- Folio ${a.folio} (${a.clasificacion}) de ${a.vendedor}: ${a.dias} días vs SLA ${a.slaLimit}. Estatus: ${a.estatus}`)
    .join("\n");

  return [
    "Eres el analista de operaciones de Holtmont. Analiza los KPIs de cotizaciones del periodo " +
    metrics.month + "/" + metrics.year + " y responde en español en aproximadamente 180 palabras.",
    "",
    "DATOS:",
    "- Cotizaciones totales: " + metrics.totalCount,
    "- Ganadas: " + metrics.winLoss.ganada + " | Perdidas: " + metrics.winLoss.perdida + " | En proceso: " + metrics.winLoss.enProceso,
    "- Tasa de cierre: " + metrics.closeRate + "%",
    "- SLA A (" + sla.A.slaLimit + " días): " + sla.A.ok + " cumplidas / " + sla.A.fail + " fuera de tiempo (promedio " + sla.A.avgDays + " días)",
    "- SLA AA (" + sla.AA.slaLimit + " días): " + sla.AA.ok + " cumplidas / " + sla.AA.fail + " fuera de tiempo (promedio " + sla.AA.avgDays + " días)",
    "- SLA AAA (" + sla.AAA.slaLimit + " días): " + sla.AAA.ok + " cumplidas / " + sla.AAA.fail + " fuera de tiempo (promedio " + sla.AAA.avgDays + " días)",
    "",
    "SLAs INCUMPLIDOS:",
    topFallas || "- Ninguno en el periodo.",
    "",
    "Entrega el texto en un solo bloque, sin listas ni markdown, y cierra siempre con una recomendación operativa concreta y accionable para el equipo de ventas."
  ].join("\n");
}

/** Llama a Gemini con el prompt de métricas. Degrada con mensaje claro si no hay key. */
function callGeminiForMetrics(prompt) {
  try {
    const key = PropertiesService.getScriptProperties().getProperty(METRICS_CONFIG.geminiKeyProperty);
    if (!key) {
      return { success: false, text: "Sin GEMINI_API_KEY configurada: el reporte se generó solo con reglas. Configúrala desde el dashboard para incluir el análisis de IA." };
    }
    const url = "https://generativelanguage.googleapis.com/v1beta/models/" +
      METRICS_CONFIG.geminiModel + ":generateContent?key=" + key;
    const response = UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      muteHttpExceptions: true,
      payload: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] })
    });
    const body = JSON.parse(response.getContentText());
    const text = body && body.candidates && body.candidates[0] &&
      body.candidates[0].content && body.candidates[0].content.parts &&
      body.candidates[0].content.parts[0] ? body.candidates[0].content.parts[0].text : "";
    if (!text) return { success: false, text: "Gemini no devolvió contenido analizable." };
    return { success: true, text: String(text).trim() };
  } catch (e) {
    return { success: false, text: "Error al consultar Gemini: " + e.toString() };
  }
}

/** AGENTE COMPLETO: reglas + Gemini + notificación. Lo dispara el dashboard. */
function runQuoteMetricsAgent(params) {
  try {
    const metrics = internalCollectQuoteMetrics(params);
    const gemini = callGeminiForMetrics(buildQuoteMetricsPrompt(metrics));

    const lastRun = {
      timestamp: new Date().toISOString(),
      month: metrics.month,
      year: metrics.year,
      alerts: metrics.alerts,
      geminiSummary: gemini.text,
      geminiOk: gemini.success,
      metrics: metrics
    };

    try {
      PropertiesService.getScriptProperties()
        .setProperty(METRICS_CONFIG.lastReportProperty, JSON.stringify(lastRun));
    } catch (e) {
      console.warn("No se pudo persistir el último reporte: " + e.toString());
    }

    try {
      NotifierService.sendToOutlook({
        evento: "REPORTE_METRICAS_COTIZACIONES",
        origen: "tabla de ventas",
        periodo: metrics.month + "/" + metrics.year,
        email: resolveUserEmail("ANTONIA_VENTAS"),
        tasaCierre: metrics.closeRate,
        alertas: metrics.alerts.length,
        resumen: gemini.text,
        enviadoEn: new Date().toISOString()
      });
    } catch (e) { /* la notificación nunca bloquea al agente */ }

    registrarLog((params && params.username) || "SISTEMA", "AGENTE_METRICAS",
      `Periodo ${metrics.month}/${metrics.year} · ${metrics.alerts.length} alertas · cierre ${metrics.closeRate}%`);

    return { success: true, lastRun: lastRun };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/** Versión para disparador diario/semanal: ejecuta el agente y vuelca el KPI a la hoja. */
function autoUpdateQuoteMetrics() {
  const now = new Date();
  const params = { month: now.getMonth() + 1, year: now.getFullYear() };
  const res = runQuoteMetricsAgent(params);
  if (res.success) {
    try { apiWriteQuoteMetricsToSheet(params); } catch (e) { console.warn(e.toString()); }
  }
  return res;
}

/** Vuelca las métricas a la hoja KPI_COTIZACIONES. */
function apiWriteQuoteMetricsToSheet(params) {
  try {
    const metrics = internalCollectQuoteMetrics(params);
    let sheet = findSheetSmart(METRICS_CONFIG.kpiSheetName);
    if (!sheet) sheet = SS.insertSheet(METRICS_CONFIG.kpiSheetName);
    sheet.clearContents();

    const rows = [
      ["KPI COTIZACIONES", "PERIODO", metrics.month + "/" + metrics.year, "GENERADO", new Date()],
      [],
      ["INDICADOR", "VALOR"],
      ["Cotizaciones totales", metrics.totalCount],
      ["Ganadas", metrics.winLoss.ganada],
      ["Perdidas", metrics.winLoss.perdida],
      ["En proceso", metrics.winLoss.enProceso],
      ["Tasa de cierre (%)", metrics.closeRate],
      [],
      ["CLASE", "SLA (días)", "TOTAL", "EN TIEMPO", "FUERA DE SLA", "PROMEDIO DÍAS", "% CUMPLIMIENTO"]
    ];
    ["A", "AA", "AAA"].forEach(c => {
      const s = metrics.slaSummary[c];
      rows.push([c, s.slaLimit, s.count, s.ok, s.fail, s.avgDays, s.pctOk]);
    });
    rows.push([]);
    rows.push(["COTIZADOR", "TOTAL", "GANADAS", "PERDIDAS", "EN PROCESO"]);
    metrics.byCotizadorArr.forEach(v => rows.push([v.nombre, v.total, v.ganada, v.perdida, v.enProceso]));

    const width = rows.reduce((m, r) => Math.max(m, r.length), 1);
    const normalized = rows.map(r => r.concat(new Array(width - r.length).fill("")));
    sheet.getRange(1, 1, normalized.length, width).setValues(normalized);
    SpreadsheetApp.flush();

    return { success: true, message: "KPI_COTIZACIONES actualizado", rows: normalized.length };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/** Último reporte guardado del agente (para pintar el dashboard al entrar). */
function apiGetLastAgentReport() {
  try {
    const raw = PropertiesService.getScriptProperties().getProperty(METRICS_CONFIG.lastReportProperty);
    if (!raw) return { success: true, hasReport: false, lastRun: null };
    return { success: true, hasReport: true, lastRun: JSON.parse(raw) };
  } catch (e) {
    return { success: false, hasReport: false, message: e.toString() };
  }
}

/** Guarda la GEMINI_API_KEY en Propiedades del Script. */
function apiSaveGeminiKey(key) {
  try {
    const clean = String(key || "").trim();
    if (!clean) return { success: false, message: "La key no puede estar vacía." };
    PropertiesService.getScriptProperties().setProperty(METRICS_CONFIG.geminiKeyProperty, clean);
    registrarLog("ADMIN", "GEMINI_KEY", "Se actualizó la API Key de Gemini");
    return { success: true, message: "Key guardada" };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/** ¿Hay key configurada? Devuelve solo un preview, nunca la key completa. */
function apiCheckGeminiKey() {
  try {
    const key = PropertiesService.getScriptProperties().getProperty(METRICS_CONFIG.geminiKeyProperty);
    if (!key) return { success: true, hasKey: false, keyPreview: "" };
    return { success: true, hasKey: true, keyPreview: String(key).substring(0, 6) + "***" };
  } catch (e) {
    return { success: false, hasKey: false, message: e.toString() };
  }
}

/** Agente de productividad por persona sobre los trackers del directorio. */
function runTrackerProductivityAgent(params) {
  try {
    const opts = params || {};
    const month = opts.month ? parseInt(opts.month, 10) : (new Date().getMonth() + 1);
    const year = opts.year ? parseInt(opts.year, 10) : new Date().getFullYear();

    const directory = getDirectoryFromDB() || [];
    const seen = {};
    const people = [];
    directory.forEach(u => {
      const name = String(u.name || "").trim();
      if (!name || seen[name.toUpperCase()]) return;
      seen[name.toUpperCase()] = true;
      people.push({ name: name, dept: u.dept || "GENERAL" });
    });

    const resumen = [];
    let totalActivas = 0, totalCerradas = 0;

    people.forEach(person => {
      if (!findSheetSmart(person.name)) return;
      const res = internalFetchSheetData(person.name);
      if (!res.success) return;

      const enPeriodo = (row) => {
        const f = parseSheetDate(pickTaskValue(row, ["FECHA", "FECHA ALTA", "ALTA", "FECHA INICIO"]));
        if (!f) return false;
        return (f.getMonth() + 1) === month && f.getFullYear() === year;
      };

      const activas = (res.data || []).filter(enPeriodo);
      const cerradas = (res.history || []).filter(enPeriodo);
      if (activas.length === 0 && cerradas.length === 0) return;

      const vencidas = activas.filter(row => {
        const clase = String(pickTaskValue(row, ["CLASIFICACION", "CLASI"]) || "").toUpperCase().trim();
        const limite = METRICS_CONFIG.slaLimits[clase];
        if (!limite) return false;
        const f = parseSheetDate(pickTaskValue(row, ["FECHA", "FECHA ALTA", "ALTA"]));
        if (!f) return false;
        return Math.floor((new Date().getTime() - f.getTime()) / 86400000) > limite;
      }).length;

      totalActivas += activas.length;
      totalCerradas += cerradas.length;

      resumen.push({
        nombre: person.name,
        departamento: person.dept,
        activas: activas.length,
        cerradas: cerradas.length,
        vencidas: vencidas,
        cumplimiento: (activas.length + cerradas.length)
          ? Math.round((cerradas.length / (activas.length + cerradas.length)) * 1000) / 10
          : 0
      });
    });

    resumen.sort((a, b) => b.cerradas - a.cerradas);

    const notif = NotifierService.sendToOutlook({
      evento: "REPORTE_PRODUCTIVIDAD_TRACKER",
      origen: "tracker general",
      periodo: month + "/" + year,
      email: resolveUserEmail("LUIS_CARLOS"),
      totalActivas: totalActivas,
      totalCerradas: totalCerradas,
      personas: resumen.length,
      enviadoEn: new Date().toISOString()
    });

    registrarLog((opts.username) || "SISTEMA", "AGENTE_PRODUCTIVIDAD",
      `Periodo ${month}/${year} · ${resumen.length} personas`);

    return {
      success: true,
      data: {
        month: month,
        year: year,
        totalActivas: totalActivas,
        totalCerradas: totalCerradas,
        personas: resumen,
        emailSent: !!(notif && notif.success)
      }
    };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

// ----------------------------------------------------------------------
// G. APIs SUELTAS QUE INVOCA index.html
// ----------------------------------------------------------------------

/** Re-sincroniza DB_DIRECTORY con INITIAL_DIRECTORY sin borrar altas manuales. */
function apiResyncDirectory() {
  const lock = LockService.getScriptLock();
  try {
    if (!lock.tryLock(10000)) return { success: false, message: "Sistema ocupado, intenta de nuevo." };

    let sheet = findSheetSmart(APP_CONFIG.directorySheetName);
    if (!sheet) sheet = SS.insertSheet(APP_CONFIG.directorySheetName);

    const values = sheet.getDataRange().getValues();
    const existing = {};
    for (let i = 1; i < values.length; i++) {
      const name = String(values[i][0] || "").trim().toUpperCase();
      const dept = String(values[i][1] || "").trim().toUpperCase();
      if (name) existing[name + "|" + dept] = true;
    }

    const missing = INITIAL_DIRECTORY.filter(u =>
      !existing[String(u.name).toUpperCase().trim() + "|" + String(u.dept).toUpperCase().trim()]);

    if (values.length < 2) {
      sheet.clear();
      sheet.appendRow(["NOMBRE", "DEPARTAMENTO", "TIPO_HOJA"]);
    }
    if (missing.length > 0) {
      const startRow = Math.max(sheet.getLastRow() + 1, 2);
      sheet.getRange(startRow, 1, missing.length, 3)
        .setValues(missing.map(u => [u.name, u.dept, u.type]));
      SpreadsheetApp.flush();
    }

    registrarLog("ADMIN", "RESYNC_DIRECTORIO", `${missing.length} registros agregados`);
    return {
      success: true,
      message: missing.length
        ? `Directorio sincronizado: ${missing.length} registro(s) agregado(s).`
        : "El directorio ya estaba sincronizado."
    };
  } catch (e) {
    return { success: false, message: e.toString() };
  } finally {
    lock.releaseLock();
  }
}

/** Auditoría de cambios de fecha en la tabla de ventas. */
function apiLogDateChange(payload, username) {
  try {
    const p = payload || {};
    registrarLog(
      username || "DESCONOCIDO",
      "CAMBIO_FECHA",
      `Hoja: ${p.hoja || "-"} | Folio: ${p.folio || "-"} | Campo: ${p.campo || "-"} | ${p.anterior || "(vacío)"} -> ${p.nuevo || "(vacío)"}`
    );
    return { success: true };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/** Empresas (clientes) con cotizaciones en un año/mes dados, para el Banco de Información. */
function apiFetchInfoBankCompanies(year, monthName) {
  try {
    const res = internalFetchSheetData(SALES_ROUTING_CONFIG.masterSalesSheet);
    if (!res.success) return { success: false, message: res.message };

    const monthMap = {
      'ENERO': 0, 'FEBRERO': 1, 'MARZO': 2, 'ABRIL': 3, 'MAYO': 4, 'JUNIO': 5,
      'JULIO': 6, 'AGOSTO': 7, 'SEPTIEMBRE': 8, 'OCTUBRE': 9, 'NOVIEMBRE': 10, 'DICIEMBRE': 11
    };
    const targetYear = parseInt(year, 10) || new Date().getFullYear();
    let targetMonth = monthMap[String(monthName).toUpperCase().trim()];
    if (targetMonth === undefined) {
      const numeric = parseInt(monthName, 10);
      targetMonth = isNaN(numeric) ? undefined : numeric - 1;
    }
    if (targetMonth === undefined) return { success: false, message: "Mes inválido: " + monthName };

    const companies = {};
    (res.data || []).concat(res.history || []).forEach(row => {
      const cliente = String(pickTaskValue(row, ["CLIENTE"]) || "").trim();
      if (!cliente) return;
      // El banco agrupa por F. INICIO (decisión del dueño, 2026-08-15): se
      // reutilizan los alias del calendario y FECHA/ALTA quedan de respaldo
      // para las hojas viejas, que no tienen columna de inicio.
      const fecha = parseSheetDate(pickTaskValue(row, BANK_DATE_ALIASES));
      if (!fecha) return;
      if (fecha.getMonth() !== targetMonth || fecha.getFullYear() !== targetYear) return;
      const key = cliente.toUpperCase();
      if (!companies[key]) companies[key] = { name: cliente.toUpperCase(), count: 0 };
      companies[key].count++;
    });

    return {
      success: true,
      data: Object.keys(companies).map(k => companies[k]).sort((a, b) => a.name.localeCompare(b.name))
    };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/**
 * Agencia de agentes de texto (Paperclip). En GAS se resuelve con Gemini;
 * el stack de Python expone el mismo contrato en /api/run_paperclip_agency.
 */
function runPaperclipAgents(requestText) {
  try {
    const texto = String(requestText || "").trim();
    if (!texto) return { success: false, message: "Se requiere texto de entrada." };

    const prompt = [
      "Eres la agencia de agentes de Holtmont. Analiza la siguiente solicitud de obra",
      "y responde en español con: (1) resumen ejecutivo, (2) alcance sugerido,",
      "(3) riesgos detectados y (4) una recomendación operativa final.",
      "",
      "SOLICITUD:",
      texto
    ].join("\n");

    const gemini = callGeminiForMetrics(prompt);
    if (!gemini.success) return { success: false, message: gemini.text };

    registrarLog("SISTEMA", "PAPERCLIP_AGENTS", texto.substring(0, 120));
    return { success: true, result: gemini.text, output: gemini.text };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}
