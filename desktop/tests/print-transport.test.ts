/**
 * Testes do transporte de impressão RAW (F10.7): dist/main/print-transport.js.
 *
 * Não há impressora nos testes: o PowerShell é injetado. Cobre montagem dos
 * argumentos, sucesso, falha do spooler (com a mensagem real do script),
 * payload vazio, impressora não escolhida e limpeza do arquivo temporário.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import fs from "node:fs";
import os from "node:os";
import { createRequire } from "node:module";

const req = createRequire(__filename);
const { buildPrintArgs, printRawBytes, ensureScriptFile } = req(
    path.resolve(__dirname, "../dist/main/print-transport.js")
);

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "gasflow-print-test-"));

test("buildPrintArgs passa impressora e arquivo para o PowerShell", () => {
    const args = buildPrintArgs("C:\\x\\raw.ps1", "GT710", "C:\\tmp\\cupom.bin");

    assert.deepEqual(args.slice(0, 5), ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File"]);
    assert.equal(args[5], "C:\\x\\raw.ps1");
    assert.equal(args[6], "-PrinterName");
    assert.equal(args[7], "GT710");
    assert.equal(args[8], "-FilePath");
    assert.equal(args[9], "C:\\tmp\\cupom.bin");
});

test("o script PowerShell materializado contém o P/Invoke do spooler", () => {
    const scriptPath = ensureScriptFile(TMP);
    const content = fs.readFileSync(scriptPath, "utf-8");

    assert.ok(fs.existsSync(scriptPath), "script deveria existir em disco");
    // DATATYPE RAW é o que faz os bytes ESC/POS chegarem crus na térmica
    assert.match(content, /pDataType = "RAW"/);
    assert.match(content, /winspool\.Drv/);
    assert.match(content, /WritePrinter/);
});

test("sucesso: grava os bytes e confirma", async () => {
    let seen: { args: readonly string[]; size: number } | null = null;
    const exec = async (_file: string, args: readonly string[]) => {
        const binPath = args[args.indexOf("-FilePath") + 1];
        seen = { args, size: fs.statSync(binPath).size };
        return { code: 0, stdout: "", stderr: "" };
    };

    const data = Buffer.from("\x1b@CUPOM", "utf-8");
    const result = await printRawBytes("GT710", data, { exec: exec as never, tmpDir: TMP });

    assert.equal(result.ok, true);
    assert.equal(seen!.size, data.length, "o arquivo temporário leva os bytes ESC/POS");
    assert.equal(seen!.args[seen!.args.indexOf("-PrinterName") + 1], "GT710");
    // Arquivo temporário removido depois do envio
    const leftover = fs.readdirSync(TMP).filter((f) => f.startsWith("gasflow-print-"));
    assert.deepEqual(leftover, []);
});

test("falha do spooler devolve a mensagem do script", async () => {
    const exec = async () => ({
        code: 1,
        stdout: "",
        stderr: "OpenPrinter falhou (impressora não encontrada: GT710)",
    });

    const result = await printRawBytes("GT710", Buffer.from("x"), { exec: exec as never, tmpDir: TMP });

    assert.equal(result.ok, false);
    assert.match(result.error!, /impressora não encontrada/);
});

test("sem impressora escolhida: nem tenta imprimir", async () => {
    let called = false;
    const exec = async () => {
        called = true;
        return { code: 0, stdout: "", stderr: "" };
    };

    const result = await printRawBytes("   ", Buffer.from("x"), { exec: exec as never, tmpDir: TMP });

    assert.equal(result.ok, false);
    assert.match(result.error!, /não configurada/);
    assert.equal(called, false);
});

test("payload vazio é recusado (não manda papel em branco)", async () => {
    const result = await printRawBytes("GT710", Buffer.alloc(0), { tmpDir: TMP });

    assert.equal(result.ok, false);
    assert.match(result.error!, /vazio/);
});
