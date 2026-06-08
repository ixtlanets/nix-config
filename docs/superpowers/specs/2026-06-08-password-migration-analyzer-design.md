# Password Migration Analyzer Design

## Goal

Build a read-only analyzer for a migration from 1Password to Apple Passwords
with `pass` as the eventual Linux/offline mirror. The first deliverable must
only compare exports and produce a local report. It must not import into Apple
Passwords, write to `pass`, mutate source exports, or commit generated reports.

The analyzer should help decide which 1Password items can be safely imported
into Apple Passwords and which require manual review because an Apple Passwords
item already exists.

## Inputs

The analyzer reads two required local plaintext export files supplied by the
user:

- Apple Passwords CSV, exported from Passwords.app.
- 1Password `.1pux`, exported from 1Password.

It may also read one optional source:

- `pass` password store, typically `~/.password-store`.

Both files are sensitive. The tool should treat every input field as secret by
default and should avoid printing or persisting raw passwords, OTP secrets,
notes, recovery codes, or full usernames unless explicitly needed for
disambiguation.

## Outputs

The analyzer writes a report directory outside the repository, typically under
`~/tmp/password-migration-report`.

The report should contain:

- `summary.md`: aggregate counts, major findings, and recommended next steps.
- `safe-import.csv`: Apple-compatible CSV containing only records that appear
  safe to import into Apple Passwords. This file is still sensitive because it
  contains passwords and OTPAuth URLs.
- `conflicts.csv`: review table with conflict categories and redacted evidence.
- `pass-coverage.csv`: optional review table for `pass` coverage and drift when
  a password store path is supplied.
- `review.md`: human-readable review notes grouped by conflict class.

The analyzer should not commit these outputs. The report directory should be
created with private permissions where possible.

## Matching Model

The primary matching key is:

```text
normalized registrable domain + normalized username
```

Normalization should:

- lower-case domains and usernames;
- strip leading and trailing whitespace;
- strip URL schemes, paths, query strings, fragments, and common `www.`
  prefixes when computing the primary domain key;
- preserve the original URL for report evidence and export output;
- tolerate missing usernames by classifying matches as ambiguous rather than
  automatically safe.

The initial implementation can use hostname normalization without a public
suffix list. A later iteration may add a public suffix parser if false matches
around multi-part suffixes become a real problem.

Additional non-primary signals should be used for reporting:

- title similarity;
- URL hostname overlap;
- password equality as a boolean only;
- OTPAuth equality as a boolean only;
- OTP presence in each source;
- multiple URLs in the 1Password item;
- missing or empty usernames.

## Conflict Classes

The analyzer should assign each 1Password login item to one primary class:

- `safe_import`: no likely Apple Passwords match exists.
- `already_present`: Apple has a matching item and password/OTP state appears
  equivalent.
- `apple_missing_otp`: Apple has a matching item, but 1Password has OTPAuth and
  Apple does not.
- `password_differs`: Apple has a matching item, but the password differs.
- `otp_differs`: Apple and 1Password both have OTPAuth, but the OTPAuth values
  differ.
- `ambiguous_match`: one or more weak Apple matches exist, but the primary key
  is incomplete or inconclusive.
- `unsupported_item`: the 1Password item is not a login item that can be mapped
  into Apple Passwords CSV.

Apple-only records should be counted and summarized separately. They should not
appear in `safe-import.csv`.

Existing `pass` records should be counted and summarized separately. They should
not create Apple import candidates by themselves.

## 1Password Mapping

The analyzer should read `.1pux` as a zip archive and parse its JSON contents.
It should focus on login items first. For each login item, extract:

- title;
- primary username field;
- primary password field;
- one or more URLs;
- notes, redacted in reports;
- TOTP/one-time password field when present;
- vault name or item metadata when available for review context.

If multiple URLs exist, choose the first usable URL as the Apple CSV `URL` value
and mention the extra URL count in review output. The eventual `pass` importer
can preserve all URLs, but this analyzer only needs enough data to assess Apple
import safety.

## Apple Mapping

The analyzer should parse Apple Passwords CSV with these expected columns:

```text
Title, URL, Username, Password, Notes, OTPAuth
```

The tool should validate the header and stop with a clear error if required
columns are missing. It should preserve Apple rows only in memory for matching.

## Pass Mapping

The analyzer should support an optional `--pass-store` argument. In the default
mode it should only inspect encrypted entry names on disk and should not decrypt
any `pass` entries.

Default `pass` analysis should:

- count entries in the password store;
- derive normalized domain and username hints from entry paths;
- classify obvious non-login namespaces such as `api`, `cards`, `notes`, `ssh`,
  `server`, and `secrets`;
- report likely coverage where a 1Password or Apple item appears to have a
  matching `pass` path;
- report `pass_only` entries separately so migration work does not delete or
  duplicate them.

The analyzer may later add an explicit deep mode, such as
`--pass-decrypt-readonly`. Deep mode may decrypt entries read-only to detect
password and OTP presence, compare values in memory, and improve drift
classification. Even in deep mode, reports must not include raw passwords,
OTPAuth URLs, OTP secrets, notes, or recovery codes.

## Redaction

Reports should never include raw:

- passwords;
- OTPAuth URLs or OTP secrets;
- notes;
- recovery codes;
- full plaintext export rows.

Review output may include:

- title;
- normalized domain;
- username fingerprint or partially redacted username;
- booleans such as `password_same`, `otp_same`, `apple_has_otp`,
  `onepassword_has_otp`;
- length metadata such as password length;
- counts such as number of URLs.

If stable identifiers are useful, use short hashes computed in memory from
source values. Hashes are only for matching/debugging within the report and are
not a security boundary.

## Safety

The analyzer must be read-only with respect to Apple Passwords, 1Password, and
`pass`. It should fail before writing reports if an output path is inside the
repository unless the user explicitly overrides that behavior.

The tool should remind the user that `safe-import.csv` is plaintext-sensitive
and should be deleted after use.

## Validation

Initial validation should cover:

- parsing a real Apple Passwords CSV header;
- parsing a real `.1pux` archive structure without printing secrets;
- optionally scanning a real `pass` store without decrypting entries;
- producing a report from the supplied exports;
- confirming that generated reports contain no raw password or OTPAuth values
  except for `safe-import.csv`, which is intentionally importable and sensitive;
- running a dry report generation twice to confirm deterministic output.

No Apple import, `pass` mutation, or git operation against the password store is
part of this phase.
