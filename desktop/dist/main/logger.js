"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.logger = void 0;
exports.setRendererSender = setRendererSender;
exports.logLine = logLine;
const electron_log_1 = __importDefault(require("electron-log"));
let send = null;
/** Registra a função que entrega linhas ao renderer (chamado no webContents did-finish-load). */
function setRendererSender(fn) {
    send = fn;
}
function logLine(level, scope, message) {
    const text = `[${new Date().toISOString()}] [${scope}] ${message}`;
    if (level === "error")
        electron_log_1.default.error(text);
    else if (level === "warn")
        electron_log_1.default.warn(text);
    else
        electron_log_1.default.info(text);
    send?.("gasflow:log", { level, scope, message: text, ts: Date.now() });
}
exports.logger = {
    info: (scope, message) => logLine("info", scope, message),
    warn: (scope, message) => logLine("warn", scope, message),
    error: (scope, message) => logLine("error", scope, message),
};
//# sourceMappingURL=logger.js.map
