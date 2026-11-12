# HealthSync

A small personal iPhone app that copies my Apple Health data into my own database, quietly, in the background.

To look at the data afterwards, there's a local dashboard in [`../dashboard/`](../dashboard/).

I wanted all my health data (steps, workouts, heart, sleep, nutrition, mobility, symptoms, vitals and the rest) somewhere I control and can query, without paying a subscription and without the data passing through anyone else's servers. This is the result.

---

## What it does

- Reads every kind of Apple Health data the iOS SDK exposes as samples: 189 types (119 measurements, 69 categories, plus workouts). Read-only — it never writes to Health.
- The list lives in `HealthSync/HealthTypes.json`, generated from Apple's SDK by `scripts/generate-type-catalog.swift`, with one fixed unit per type and whether it adds up (steps) or averages (heart rate). The dashboard reads the same file. Not included yet: GPS workout routes, ECGs, hearing tests and clinical records, which each need their own code.
- Uploads new samples to a Supabase Postgres table as they're recorded. iOS wakes the app in the background when Health gets new data; opening the app also catches up.
- Mirrors deletions too: delete a sample in Health and it disappears from the database on the next sync.
- Picks up exactly where it left off. If an upload fails or the phone is locked, nothing is lost — it just tries again next time.

There's no login screen. On first launch the app creates an anonymous account for itself and keeps it in the iPhone Keychain. The screen shows that account's ID, which is the `user_id` on every row in the table.

## How we got here

This went through a few versions, and the reasoning is worth keeping:

1. **Supabase + Sign in with Apple.** The first design. Turned out Sign in with Apple needs a paid ($99/yr) Apple Developer account.
2. **CloudKit (iCloud).** Technically the nicest option — end-to-end encrypted, no server, no login. Also needs the paid account. The code is still here (`CloudStore.swift`) in case I ever pay.
3. **Supabase + anonymous sign-in, on a free Apple ID.** What's running now. The free account has one big catch: apps you install yourself stop opening after 7 days. So there's a script on the Mac that renews and reinstalls the app automatically before that happens (see below).

## Setting it up from scratch

You need a Mac with Xcode, an iPhone, and a free Supabase project.

Everything below runs from this folder (`apple-health-sync/` in the dashboard repo).

1. **Supabase** (your own project — every user brings their own database)
   - SQL Editor → run `supabase/schema.sql`.
   - Authentication → Sign In / Providers → turn on **Allow anonymous sign-ins**.
2. **Local config** (both files are gitignored, so your values never end up in a commit)
   - `cp Config/Secrets.example.xcconfig Config/Secrets.xcconfig` and fill in:
     - the Supabase URL and the **publishable** key (never the secret key),
     - `BUNDLE_ID_PREFIX` — anything reverse-domain-ish that's yours, e.g. `com.yourname`. The app becomes `com.yourname.HealthSync`. Pick once; changing it later means a "new" app on the phone,
     - `DEVELOPMENT_TEAM` — your Team ID. Easiest way to find it: open the project in Xcode, pick your Apple ID under Signing & Capabilities → Team, then run `xcodebuild -showBuildSettings | grep DEVELOPMENT_TEAM`.
   - `cp scripts/local.env.example scripts/local.env` and fill in your iPhone's IDs (`xcrun devicectl list devices`).
3. **Build**: `brew install xcodegen && xcodegen && open HealthSync.xcodeproj`, then run on the phone.
4. **On the iPhone**: Settings → General → VPN & Device Management → trust your Apple ID. Turn on Developer Mode if asked. Open the app → **Connect Apple Health**.

## Staying installed on a free Apple ID

Free signing lasts 7 days. `scripts/resign-and-install.sh` checks how long the copy on the phone has left; under 60 hours, it gets a fresh 7-day profile from Apple, rebuilds, and reinstalls (USB or Wi-Fi). App data survives the reinstall.

`scripts/install-agent.sh` sets up a LaunchAgent that runs it at 9:00, 15:00 and 21:00. In practice it does real work about every 4–5 days.

- Log: `~/Library/Logs/HealthSync-resign.log` (failures also pop a macOS notification)
- Force a renewal: `FORCE_RENEW=1 scripts/resign-and-install.sh`
- Turn it off: `launchctl bootout gui/$(id -u)/local.healthsync.resign`

It needs the Mac to be on (or wake up) and the phone reachable at least once in each 60-hour window.

## How the data is protected

| Where | What protects it |
|---|---|
| In transit | TLS 1.3 minimum. Ephemeral network session, so nothing gets cached on disk. |
| Who can read it | Postgres Row-Level Security. Each account can only see, add and delete its **own** rows. Anonymous visitors get nothing. |
| Changing history | Not possible — there's no UPDATE permission at all. Rows are write-once. |
| On the server | Supabase encrypts its disks (AES-256). |
| On the phone | The app never stores health data itself. Its bookmarks use iOS Data Protection; the login session is in the Keychain. |
| Logs | Health values are never logged. |
| Least data | Read-only Health access, no metadata uploaded (see `sanitizedMetadata` in `SampleMapper.swift`), and you choose exactly which types to allow in iOS's permission sheet. |

One honest caveat: unlike the CloudKit version, this isn't end-to-end encrypted. Supabase (and anyone with my dashboard login) can read the rows. Protect the Supabase account with a strong password and 2FA.

## Security review (Nov 2026)

Before pushing this to GitHub I went through it from an attacker's point of view. Here's what turned up and what changed.

**Fixed**

- **Project URL, API key and Team ID were hard-coded in `Config.swift`.** They now live in `Config/Secrets.xcconfig`, which is gitignored and injected at build time. The publishable key is designed to be public, but there's no reason to publish it. The app also refuses to start if someone ever puts a *secret* key in there by mistake.
- **Dependencies weren't pinned.** `supabase-swift` was "any 2.x" and the lockfile wasn't going to be committed. Now it's pinned to exactly 2.55.6, `Package.resolved` is committed, and the unattended re-sign script builds with `-onlyUsePackageVersionsFromResolvedFile` so it can never quietly pull in a new (possibly compromised) version.
- **Junk-data abuse.** Anonymous sign-ups are open, so anyone holding the public key could create an account and stuff the table with junk (they still couldn't see my data). `schema.sql` now caps row sizes. **To apply this, re-run `supabase/schema.sql` in the SQL Editor** — it's safe to run again.
- **Personal device IDs and home-folder paths** were in the scripts. They're now in a gitignored `scripts/local.env` and filled into the LaunchAgent by `install-agent.sh`.

**Checked and fine**

- No secret/service-role key anywhere. Only the publishable key, which is useless without Row-Level Security letting it in.
- Without a session, the table returns `permission denied` (verified against the live project).
- RLS policies: select/insert/delete restricted to `auth.uid() = user_id`; `user_id` is filled by the database, not the app; no UPDATE grant.
- No App Transport Security exceptions, no custom URL schemes, no `print`/`NSLog` of data.
- Dependencies (7 total) all come from Supabase, Apple and Point-Free — see `Package.resolved`. I didn't check them against a vulnerability database; GitHub's Dependabot can do that once it's enabled on the repo.

**Not done yet / worth knowing**

- **Live attack test.** `scripts/rls-check.py` plays the attacker against the real database: makes a throwaway account and tries to read, forge, edit and delete other rows. It wasn't run during the review. Run it yourself with `python3 -I scripts/rls-check.py`; every line should say PASS. It leaves one test user behind to delete in Authentication → Users.
- The Keychain login is restorable from an encrypted backup to a new phone (`AfterFirstUnlock`, not `ThisDeviceOnly`). That's deliberate — it keeps the same account after upgrading phones.
- Debug builds carry the `get-task-allow` entitlement (normal for apps installed from Xcode).
- If the Keychain session is ever lost (e.g. the phone is erased without a backup), the app starts a new account. Old rows stay in the table, visible in the dashboard.

## Handy SQL

```sql
-- Is background sync working? (look for recent uploads you didn't trigger)
select type, max(end_date) as latest_recorded, max(uploaded_at) as latest_upload, count(*)
from health_samples group by type order by latest_upload desc;
```

## License

MIT — see [LICENSE](LICENSE). This applies to the `apple-health-sync/` folder only.

## If I ever pay for the developer account

Switch to CloudKit for end-to-end encryption and drop the 7-day dance: set `Backends.current = CloudStore()` in `HealthBackend.swift`, uncomment the iCloud lines in `project.yml`, put the paid Team ID in `Secrets.xcconfig`, run `xcodegen`, and remove the LaunchAgent.
