import fs from 'node:fs';
import { cleanOrphanMemberships, deleteLidContacts, dedupeByName, type DedupeResult } from './db';

/**
 * Deduplicação da base de contatos:
 * 1. Remove JIDs @lid (identificador interno do multi-device, sem nome/telefone real).
 * 2. Consolida nomes repetidos mantendo a linha mais antiga (menor id),
 *    migrando memberships para a linha mantida.
 * Gera relatório em export/duplicados-excluidos-*.json para auditoria manual.
 */
export function runDedupe(): DedupeResult & { reportFile: string | null } {
  const lid = deleteLidContacts();
  const { result: nameMergedGroups, removed } = dedupeByName();
  cleanOrphanMemberships();

  const lidRemoved = lid.removed;
  const lidKept = lid.kept;

  let reportFile: string | null = null;
  if (lidRemoved > 0 || lidKept > 0 || removed.length > 0) {
    try {
      fs.mkdirSync('export', { recursive: true });
      reportFile = `export/duplicados-excluidos-${Date.now()}.json`;
      fs.writeFileSync(
        reportFile,
        JSON.stringify(
          {
            generatedAt: new Date().toISOString(),
            lidRemoved,
            lidKeptForCustomer: lidKept,
            lidMigrated: lid.migrated,
            mergedByName: removed,
          },
          null,
          2,
        ),
      );
    } catch {
      reportFile = null; // falha ao gravar relatório não deve bloquear a deduplicação
    }
  }

  console.log(
    `[dedupe] @lid removidos: ${lidRemoved} | @lid mantidos (com customer): ${lidKept} | grupos consolidados por nome: ${nameMergedGroups} | linhas removidas: ${removed.length}`,
  );

  return { lidRemoved, lidKept, nameMergedGroups, nameRemoved: removed.length, reportFile };
}
