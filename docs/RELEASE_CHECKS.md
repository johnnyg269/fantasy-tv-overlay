# Initial public source validation

The initial public package was prepared with synthetic fixtures and private-data checks. No account credentials, device pairing or live TV operations are needed to run its ordinary test suites.

| Component | Recorded result |
| --- | --- |
| Backend adapters, authorization and feed boundaries | 25 Python tests passed |
| Samsung controller, scenes, metadata and setup guardrails | 191 Python tests passed |
| Optional signed voice bridge | 29 Python tests passed |
| Optional AirPlay pairing/storage helper | 5 mocked Python tests passed |
| Samsung native policy/font/image/gradient checks | 88 assertions passed; native renderer build succeeded |
| Android feed/parser/policy | 26 Java tests passed |
| Official Android CI SDK bootstrap | 5 Python tests passed; pinned archive integrity/extraction verified |
| Android packaging and static checks | Debug APK build succeeded; lint reported zero errors |
| Repo-local agent skills | Both passed the skill-creator validator; setup guidance received an independent scenario check |

These are software results, not a universal device-compatibility claim. Run [the acceptance checklist](VALIDATION.md) on your own installation. The source includes pinned dependency download checks; SDKs, root binaries, generated APKs and private signing/pairing files are not distributed in the repository.

## Publication checks

The outgoing file inventory was reviewed independently and passed the repository's publication-boundary checker. An additional in-memory comparison against the original installation's private identity/configuration values found no matches in the reviewed tracked source or binary assets. None of those values were printed or added to public history. Public examples and preview artwork are synthetic. The distributed PNG artwork contains no EXIF or text metadata.

CI runs a pinned Gitleaks 8.30.1 scan over Git history, alongside source checks and the Android build. Check the Actions result for the exact commit you use; a later contribution can change the publication boundary. A clean scan reduces risk but does not establish that every dependency, device, cloud account or future setup is secure.

## What has not been established

- The generalized public Samsung package has not been physically accepted on every model or firmware. Its native overlay derives from one earlier HDMI validation; built-in apps, other firmware and cold-boot recovery need their own checks.
- Android's source, build and lint results do not prove that an OEM exposes overlay permission or that a protected video app permits the overlay. Remote focus and uninterrupted playback require physical testing.
- Fresh user ESPN/Sleeper accounts and deployment settings need private matchup verification. Yahoo and other providers need a separately implemented and verified adapter.
- The bundled real-provider adapters leave unavailable projections/probabilities explicit. Synthetic demo percentages do not establish a live prediction model.
- Cloud hosting alone does not establish computer-independent Samsung operation or TV restart recovery.
- Automatic player-to-game tuning is not shipped. App launching or program metadata alone is not tuning proof.

No formal security certification is claimed. The privacy review and source checks cover the public application boundaries described in [security and privacy](SECURITY_AND_PRIVACY.md); privileged upstream tooling, platform policy and each user's network remain separate trust boundaries.
