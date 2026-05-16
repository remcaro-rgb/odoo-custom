import { spawn } from 'node:child_process';

interface DropDatabaseArgs {
  dbName: string;
  /** PG* env overrides — same shape as pgDump's `env`. Omit to use
   *  the runner's default PGHOST/PGPORT/PGUSER/PGPASSWORD (shared cluster). */
  env?: Record<string, string>;
}

/**
 * psql -d postgres -c "DROP DATABASE <db>". -d postgres is required so
 * psql doesn't try to connect to the database it's about to drop.
 *
 * Force-drops active connections via the FORCE option (PostgreSQL 13+),
 * which is what we need on the shared cluster where Odoo workers may
 * have held lingering connections to the tenant DB.
 *
 * Idempotent: returns success if the DB doesn't exist (3D000).
 */
export async function dropDatabaseViaPg(args: DropDatabaseArgs): Promise<void> {
  const proc = spawn(
    'psql',
    [
      '-d', 'postgres',
      '-v', 'ON_ERROR_STOP=1',
      '-c', `DROP DATABASE IF EXISTS "${args.dbName}" WITH (FORCE)`,
    ],
    {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, ...(args.env ?? {}) },
    },
  );

  const err: Buffer[] = [];
  proc.stderr.on('data', (b: Buffer) => err.push(b));

  await new Promise<void>((resolve, reject) => {
    proc.on('error', reject);
    proc.on('exit', (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      const tail = Buffer.concat(err).toString('utf8');
      reject(new Error(`DROP DATABASE exited ${code}: ${tail.slice(0, 1000)}`));
    });
  });
}
