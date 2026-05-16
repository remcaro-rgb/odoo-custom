import { spawn } from 'node:child_process';
import { stat, writeFile, access } from 'node:fs/promises';
import * as path from 'node:path';

interface FilestoreTarResult {
  path: string;
  size: number;
}

/**
 * tar the tenant's filestore directory. Odoo stores attachments under
 * <filestore_base>/<dbname>/.../<sha>; the tenant slug typically matches
 * the db name on the shared pool.
 *
 * **Phase 1+ note:** the backup-runner deploys as a SEPARATE Fly app from
 * the Odoo data plane (Fly volumes are single-app), so the runner can't
 * mount Odoo's filestore directly. Filestore backup happens via the
 * `saas_filestore_backup` Odoo addon, which runs inside the Odoo container
 * and uploads its own AES-GCM-encrypted tar to S3 with a separate
 * tenant_backups row (backup_type='filestore_tar').
 *
 * That makes THIS step a no-op in production: the filestore directory
 * doesn't exist on the runner. We detect the missing directory and
 * write an empty tar so the rest of the pipeline (encrypt + upload) can
 * proceed without a special-case branch. The encrypted package's
 * filestore segment will be 0 bytes; restore tooling reads filestore
 * from the addon-produced artifact instead.
 *
 * Phase 1 atomicity caveat (preserved from the original implementation):
 * not atomic with pg_dump. If Odoo writes attachments while the tar runs,
 * those new files MAY land in the tar but their corresponding
 * `ir.attachment` rows won't be in the dump (or vice versa). Real atomicity
 * needs pgBackRest's start/stop_backup protocol.
 */
export async function filestoreTar(args: {
  slug: string;
  baseDir: string;
  outputPath: string;
}): Promise<FilestoreTarResult> {
  const tenantDir = path.join(args.baseDir, args.slug);

  // The runner's container doesn't mount Odoo's filestore. Detect the
  // missing directory and produce an empty tarball — keeps the pipeline
  // shape uniform (encrypt expects a file path with a size).
  try {
    await access(args.baseDir);
  } catch {
    // baseDir doesn't exist. Write an empty tar (just the EOF marker:
    // 1024 NUL bytes) so the encrypt step has a real file to read.
    await writeFile(args.outputPath, Buffer.alloc(1024));
    const stats = await stat(args.outputPath);
    return { path: args.outputPath, size: stats.size };
  }

  // -c  create
  // -f  output file
  // -C  change to base dir so paths inside the tar are relative
  const proc = spawn(
    'tar',
    ['-cf', args.outputPath, '-C', args.baseDir, args.slug],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

  const err: Buffer[] = [];
  proc.stderr.on('data', (c: Buffer) => err.push(c));

  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(
          new Error(
            `tar exited ${code} (dir=${tenantDir}): ${Buffer.concat(err).toString('utf8').slice(0, 4000)}`,
          ),
        );
      }
    });
  });

  const stats = await stat(args.outputPath);
  return { path: args.outputPath, size: stats.size };
}
