import { spawn } from 'node:child_process';
import { stat } from 'node:fs/promises';

interface PgDumpResult {
  path: string;
  size: number;
}

/**
 * Shell-out to pg_dump in custom format with parallel jobs. Custom format is
 * the only format that supports parallel jobs and produces a single output
 * file (instead of a directory).
 *
 * `env` overrides (Phase 3 cluster routing) are merged onto `process.env`
 * for this child only. Caller supplies the per-tenant PGHOST/PGPORT etc.;
 * absent fields fall through to the runner's default env (shared cluster).
 */
export async function pgDump(args: {
  dbName: string;
  outputPath: string;
  env?: Record<string, string>;
}): Promise<PgDumpResult> {
  // -Fc  custom format (single file, restorable with pg_restore)
  // -Z 6 zstd-ish gzip-equivalent compression level
  // -f   output file
  // NOTE: NO `-j 4`. pg_dump's `--jobs` parallel mode requires the
  // directory format (`-Fd`), not custom (`-Fc`). PostgreSQL rejects
  // with: "parallel backup only supported by the directory format".
  // For Phase 1+2 tenant sizes single-threaded -Fc is fast enough.
  // If we hit big-tenant throughput limits, switch to -Fd and adapt
  // the encrypt pipeline to walk a directory tree.
  // PG* env vars carry connection info; pg_dump reads them natively.
  const proc = spawn(
    'pg_dump',
    ['-Fc', '-Z', '6', '-f', args.outputPath, args.dbName],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, ...(args.env ?? {}) },
    },
  );

  const stderrChunks: Buffer[] = [];
  proc.stderr.on('data', (chunk: Buffer) => stderrChunks.push(chunk));

  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        const stderr = Buffer.concat(stderrChunks).toString('utf8').slice(0, 4000);
        reject(new Error(`pg_dump exited ${code}: ${stderr}`));
      }
    });
  });

  const stats = await stat(args.outputPath);
  return { path: args.outputPath, size: stats.size };
}

/**
 * Single-shot psql call to retrieve the current WAL LSN. Captured pre-dump
 * so the catalog row's `lsn_end` is approximately the upper bound of what
 * the dump observed. Not LSN-precise; see backup-tenant.ts comments.
 *
 * `env` follows the same cluster-routing override pattern as pgDump.
 */
export async function pgCurrentWalLsn(env: Record<string, string> = {}): Promise<string> {
  // -d postgres so psql doesn't default to db=$PGUSER (Postgres convention
  // when -d is omitted). The shared cluster's PGUSER is `odoo`, which is
  // a ROLE name with no matching database; the default would 500 with
  // FATAL: database "odoo" does not exist. The `postgres` maintenance
  // DB exists on every cluster and supports pg_current_wal_lsn().
  const proc = spawn(
    'psql',
    ['-d', 'postgres', '-t', '-A', '-c', 'SELECT pg_current_wal_lsn();'],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, ...env },
    },
  );

  const out: Buffer[] = [];
  const err: Buffer[] = [];
  proc.stdout.on('data', (c: Buffer) => out.push(c));
  proc.stderr.on('data', (c: Buffer) => err.push(c));

  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`psql lsn query exited ${code}: ${Buffer.concat(err).toString('utf8')}`));
    });
  });

  return Buffer.concat(out).toString('utf8').trim();
}
