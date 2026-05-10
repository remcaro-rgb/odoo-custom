# Volume resize

Stub. Procedure differs per platform:

**Railway:**
1. Railway dashboard → service → Volumes → resize. Restart required.
2. Verify with `df -h /var/lib/postgresql/data` after restart.

**Fly:**
1. `fly volumes extend <volume-id> -s <new-size-gb>`.
2. On Linux, the filesystem extends online; verify with `df -h`.

**Both:**
- Always resize *up* by at least 25% of current usage to avoid bouncing back
  into the alert threshold within a week.
- Resize the replica first, then the primary, to avoid both being offline.
