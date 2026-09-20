/**
 * PrintTransport — F10.7
 *
 * Envia bytes ESC/POS direto para a impressora instalada no Windows, usando o
 * spooler em modo RAW (winspool.drv via P/Invoke do PowerShell).
 *
 * Por que assim: a impressora térmica é USB nesta máquina e já tem driver
 * instalado. O spooler em RAW entrega os bytes sem interpretar (é o único
 * caminho para ESC/POS — `Out-Printer` renderiza texto e sai lixo). Sem
 * dependência nativa de npm: só o PowerShell que já existe no Windows.
 *
 * Nada aqui valida o hardware: erro de impressora volta como `{ok:false,error}`
 * e quem chamou (worker) reporta ao backend e mostra na tela.
 */

import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export interface RawPrintResult {
    ok: boolean;
    error?: string;
    /** ms gastos no spooler (diagnóstico). */
    durationMs?: number;
}

export type ExecFileFn = (
    file: string,
    args: readonly string[],
    options: { timeout: number; windowsHide: boolean }
) => Promise<{ code: number; stdout: string; stderr: string }>;

/**
 * Script PowerShell que manda bytes crus para uma impressora instalada.
 *
 * Mantido como constante (e materializado em disco sob demanda) para o app
 * não depender de arquivo extra no build/empacotamento.
 */
const RAW_PRINT_SCRIPT = String.raw`
param(
    [Parameter(Mandatory = $true)][string]$PrinterName,
    [Parameter(Mandatory = $true)][string]$FilePath
)
$ErrorActionPreference = "Stop"

$code = @"
using System;
using System.Runtime.InteropServices;

public class GasFlowRawPrinter {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct DOCINFOW {
        public string pDocName;
        public string pOutputFile;
        public string pDataType;
    }

    [DllImport("winspool.Drv", EntryPoint = "OpenPrinterW", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool OpenPrinter(string szPrinter, out IntPtr hPrinter, IntPtr pd);

    [DllImport("winspool.Drv", EntryPoint = "ClosePrinter", SetLastError = true)]
    public static extern bool ClosePrinter(IntPtr hPrinter);

    [DllImport("winspool.Drv", EntryPoint = "StartDocPrinterW", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool StartDocPrinter(IntPtr hPrinter, int level, ref DOCINFOW di);

    [DllImport("winspool.Drv", EntryPoint = "EndDocPrinter", SetLastError = true)]
    public static extern bool EndDocPrinter(IntPtr hPrinter);

    [DllImport("winspool.Drv", EntryPoint = "StartPagePrinter", SetLastError = true)]
    public static extern bool StartPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.Drv", EntryPoint = "EndPagePrinter", SetLastError = true)]
    public static extern bool EndPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.Drv", EntryPoint = "WritePrinter", SetLastError = true)]
    public static extern bool WritePrinter(IntPtr hPrinter, IntPtr pBytes, int dwCount, out int dwWritten);

    public static string SendBytes(string printerName, byte[] bytes) {
        IntPtr hPrinter = IntPtr.Zero;
        DOCINFOW di = new DOCINFOW();
        di.pDocName = "GasFlow";
        di.pDataType = "RAW";

        if (!OpenPrinter(printerName, out hPrinter, IntPtr.Zero)) {
            return "OpenPrinter falhou (impressora não encontrada: " + printerName + ")";
        }
        try {
            if (!StartDocPrinter(hPrinter, 1, ref di)) { return "StartDocPrinter falhou"; }
            try {
                if (!StartPagePrinter(hPrinter)) { return "StartPagePrinter falhou"; }
                try {
                    IntPtr p = Marshal.AllocCoTaskMem(bytes.Length);
                    try {
                        Marshal.Copy(bytes, 0, p, bytes.Length);
                        int written = 0;
                        if (!WritePrinter(hPrinter, p, bytes.Length, out written)) {
                            return "WritePrinter falhou";
                        }
                        if (written != bytes.Length) {
                            return "escrita parcial: " + written + " de " + bytes.Length + " bytes";
                        }
                    } finally {
                        Marshal.FreeCoTaskMem(p);
                    }
                } finally { EndPagePrinter(hPrinter); }
            } finally { EndDocPrinter(hPrinter); }
        } finally { ClosePrinter(hPrinter); }
        return "";
    }
}
"@

Add-Type -TypeDefinition $code -Language CSharp | Out-Null

$bytes = [System.IO.File]::ReadAllBytes($FilePath)
$failure = [GasFlowRawPrinter]::SendBytes($PrinterName, $bytes)
if ($failure -ne "") {
    [Console]::Error.WriteLine($failure)
    exit 1
}
exit 0
`;

/** Default de execução (injetável nos testes). */
export const defaultExecFile: ExecFileFn = (file, args, options) =>
    new Promise((resolve) => {
        execFile(file, [...args], options, (error, stdout, stderr) => {
            resolve({
                code: error ? ((error as { code?: number }).code ?? 1) : 0,
                stdout: String(stdout ?? ""),
                stderr: String(stderr ?? ""),
            });
        });
    });

let cachedScriptPath: string | null = null;

/** Materializa o script PowerShell em disco (uma vez por execução). */
export function ensureScriptFile(dir: string = os.tmpdir()): string {
    if (cachedScriptPath && fs.existsSync(cachedScriptPath)) return cachedScriptPath;
    const target = path.join(dir, "gasflow-raw-print.ps1");
    fs.writeFileSync(target, RAW_PRINT_SCRIPT, "utf-8");
    cachedScriptPath = target;
    return target;
}

/** Args do PowerShell para uma impressão (exposto para teste). */
export function buildPrintArgs(scriptPath: string, printerName: string, filePath: string): string[] {
    return [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        scriptPath,
        "-PrinterName",
        printerName,
        "-FilePath",
        filePath,
    ];
}

/**
 * Imprime `data` (ESC/POS) na impressora `printerName`.
 *
 * Nunca lança: devolve `{ok:false, error}` — o worker reporta a falha ao
 * backend em vez de derrubar o processo.
 */
export async function printRawBytes(
    printerName: string,
    data: Buffer,
    opts: { exec?: ExecFileFn; timeoutMs?: number; tmpDir?: string } = {}
): Promise<RawPrintResult> {
    const startedAt = Date.now();
    if (!printerName || !printerName.trim()) {
        return { ok: false, error: "impressora não configurada" };
    }
    if (process.platform !== "win32") {
        return { ok: false, error: `impressão RAW só é suportada no Windows (atual: ${process.platform})` };
    }
    if (!data || data.length === 0) {
        return { ok: false, error: "payload ESC/POS vazio" };
    }

    let tmpFile: string | null = null;
    try {
        const script = ensureScriptFile(opts.tmpDir);
        tmpFile = path.join(opts.tmpDir ?? os.tmpdir(), `gasflow-print-${process.pid}-${Date.now()}.bin`);
        fs.writeFileSync(tmpFile, data);

        const exec = opts.exec ?? defaultExecFile;
        const result = await exec("powershell.exe", buildPrintArgs(script, printerName, tmpFile), {
            timeout: opts.timeoutMs ?? 20_000,
            windowsHide: true,
        });

        if (result.code === 0) {
            return { ok: true, durationMs: Date.now() - startedAt };
        }
        const detail = (result.stderr || result.stdout || "").trim().split(/\r?\n/).filter(Boolean).pop();
        return {
            ok: false,
            error: detail || `powershell saiu com código ${result.code}`,
            durationMs: Date.now() - startedAt,
        };
    } catch (e) {
        return { ok: false, error: e instanceof Error ? e.message : String(e), durationMs: Date.now() - startedAt };
    } finally {
        if (tmpFile) {
            try {
                fs.unlinkSync(tmpFile);
            } catch {
                /* arquivo temporário já removido */
            }
        }
    }
}
