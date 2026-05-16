import { spawn } from 'node:child_process';

interface PgRestoreArgs {
  /** Path to the pg_dump custom-format archive on local disk. */
  dumpPath: string;
  /** Database name to restore INTO. Must already exist (pg_restore does
   *  not create the database). */
  dbName: string;
  /** Per-tenant PG* env overrides — same shape as pgDump's `env`. */
  env?: Record<string, string>;
}

/**
 * Shell-out to pg_restore in --clean mode so a re-run on a partially
 * populated target finishes cleanly.
 *
 * Flags:
 *   --dbname=<db>   target database
 *   --clean          drop objects before recreating
 *   --if-exists      no error when dropping non-existent objects
 *   --no-owner       skip ALTER OWNER commands (target may have different roles)
 *   --no-privileges  skip GRANT/REVOKE
 *   --exit-on-error  abort on first failure (default is to keep going)
 *
 * Note: pg_restore CAN do --jobs on a custom-format archive (unlike
 * pg_dump --jobs which is dir-format-only), but we leave it
 * single-threaded for Phase 3.0 small-tenant scale. Re-add `--jobs=4`
 * here when restore throughput becomes a bottleneck.
 */
export async function pgRestore(args: PgRestoreArgs): Promise<void> {
  const proc = spawn(
    'pg_restore',
    [
      `--dbname=${args.dbName}`,
      '--clean',
      '--if-exists',
      '--no-owner',
      '--no-privileges',
      '--exit-on-error',
      args.dumpPath,
    ],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, ...(args.env ?? {}) },
    },
  );

  const stderr: Buffer[] = [];
  proc.stderr.on('data', (c: Buffer) => stderr.push(c));

  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve();
      } else {
        const tail = Buffer.concat(stderr).toString('utf8').slice(0, 4000);
        reject(new Error(`pg_restore exited ${code}: ${tail}`));
      }
    });
  });
}
