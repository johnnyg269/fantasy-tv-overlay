# Verify an installation

Use synthetic scores first. Keep account identifiers, device addresses, program history and photographs containing private information out of public issues and pull requests.

The initial public package's software results and remaining limits are recorded in [RELEASE_CHECKS.md](RELEASE_CHECKS.md). Repeat the checks below for your own device and account; prior source results are not hardware acceptance.

## Feed acceptance

| Check | Expected result |
| --- | --- |
| Missing or wrong feed token | Request rejected without league data |
| Correct token | Only the configured leagues and teams are returned |
| Fresh data | Source timestamp, week, opponent, owner labels and actual totals match the provider's own UI |
| Starter lineup | Starting slots match the chosen period; bench and reserve players are excluded |
| Missing projection/probability | Unavailable is explicit; no invented values |
| Provider failure | Explicit failure; old data is not relabeled fresh |
| No arbitrary upstream URL | Configured provider IDs select a known read endpoint; client requests cannot choose an upstream host |

ESPN and Sleeper adapter tests use synthetic fixtures. A new provider also needs identity, custom-scoring, period, bye and lineup tests. Its first authenticated read must be checked against that provider's UI.

## Alert and UI acceptance

1. Start with valid scores. The first fetch establishes a quiet baseline.
2. Change either actual total. One popup appears for about five seconds, then disappears.
3. Change only projections. No score alert appears.
4. Apply a scoring correction. It triggers an alert as an actual-score change.
5. Change two leagues together. Both appear separately rather than one silently replacing the other.
6. While a popup is visible, press the remote's OK. The full sidebar opens and continues receiving updates.
7. Verify manager names, total scores, available win percentages, starters and player points. `LIVE` indicates a game in progress, not necessarily a player on the field.
8. Navigate supported league controls. Press Back. Details close and the video keeps playing.
9. Make the source stale, invalid or unreachable. No false score event occurs. The renderer releases input and hides expired state according to its implementation's stale timeout.
10. Stop the service/companion. The overlay and its input focus disappear.

Check legibility at the normal viewing distance, balanced padding, the score font, corner fade and all text lengths. A browser preview is useful visual evidence, but not a native TV rendering test.

## Playback and recovery acceptance

Repeat over every video app and input you plan to use. Verify picture, sound and remote operation. Android apps can suppress overlays; Android focus changes can alter video-app behavior. A different HDMI source lies outside an external streamer's composition.

Test companion sleep/disconnect, device sleep and TV restart separately. Record whether manual restart, re-pairing or temporary-root recovery is required. Do not call a setup always-on merely because its cloud feed stays available.

The original Samsung implementation was physically verified over HDMI. This does not validate a new user's model, firmware, built-in app or cold-boot behavior. The public Android implementation requires physical acceptance; source tests and a build alone do not prove device support.

## Optional integrations

For Alexa, test unsigned, stale and duplicate requests as well as one actual spoken invocation. An HTTP acknowledgment confirms a request, not a visible TV result. Verify that the ordinary score-alert baseline survives a manual preview.

For Apple TV metadata, verify fresh ambiguous and unavailable titles as well as a unique game title. Disconnect/sleep must clear `ON TV`. No app launch or game tuning should occur as a side effect of metadata collection.

## Reporting results

Separate four evidence levels: offline tests, successful build, simulator/device logs, and physical viewer confirmation. Include the relevant platform/app privately and the command/check results publicly only after redaction. Leave unrun checks marked unrun.
