# Nyay Saathi: Google services setup and location handoff

Prepared 20 November 2026 for the Android app and its Supabase backend. This is a setup runbook, not a deployment receipt. No Google Cloud resources, credentials, billing links, OAuth settings, or API calls were created by this document.

Target backend: `daojcrxjjkqoirqbvhjn`. Android application ID confirmed from the current project: `in.nyaysaathi.app`. Preserve the existing Vercel demo. Keep the unrelated Riva project untouched.

## 1. Create or select the Google Cloud project

1. Sign into [Google Cloud Console](https://console.cloud.google.com/) with the account that will own the product.
2. Use the project selector to create/select **Nyay Saathi**. A personal Google account can use **No organization** when offered.
3. Record the project ID and project number. A Google Cloud organization is separate from the existing Supabase organization.
4. Keep ownership with the product owner. Grant collaborators only the access needed; do not share the owner's password.

Reference: [Create a project](https://developers.google.com/workspace/guides/create-project).

## 2. Enable the relevant APIs

In the selected project, go to **APIs & Services → Library**, search each service, and select **Enable**.

| Service | Enable for | Required now? |
|---|---|---|
| Gmail API | Approved sending and optional reply monitoring | Yes |
| Google Drive API | Evidence files in each customer's Drive | Yes |
| Google Calendar API | Customer-approved case reminders and follow-ups | Added to prototype scope |
| People API | Optional birthday import beyond ordinary sign-in | Only if explicitly implementing this; not required for manual profile entry |
| Geocoding API | Translate a permitted device coordinate into a suggested region | Yes for the requested automatic region feature |
| Places API (New) | Search nearby offices/places and get current place details | Yes if including nearby-place search |
| Google Picker API | Browser-based selection of existing Drive files with narrow per-file access | Enable if that picker is implemented |
| Maps SDK for Android | A native embedded map component | Only if implementing a native map |
| Maps JavaScript API | A map rendered in the existing React/WebView UI | Only if implementing a JavaScript map |

Android location acquisition uses the platform location API and runtime permission; it does not require buying Google Geolocation API access. That Google API is a different service intended for deriving location from cell/Wi-Fi data. Do not add it solely to read Android GPS/location.

References: [Enable APIs](https://developers.google.com/workspace/guides/enable-apis), [Geolocation alternatives](https://developers.google.com/maps/documentation/geolocation/overview).

## 3. Configure billing and cost controls for Maps services

1. Open **Billing** and link an appropriate billing account to this project. The account owner enters any payment details directly in Google.
2. Open **Billing → Budgets & alerts** and create a budget scoped to this project, using the owner's chosen amount and currency. Add actual/forecast alert thresholds.
3. Open **Google Maps Platform → Quotas** and set available per-API quotas to deliberately small development limits. Choose the limits after checking which quota units each selected service exposes.
4. Have agy add authenticated per-user request limits and a server-side request cap/kill switch. Do not permit an agent to make unlimited repeated place searches or geocoding calls.
5. Check current pricing and India eligibility directly on the billing/pricing pages. Do not assume an old monthly credit makes calls free.

Geocoding and Places require billing and use usage-based pricing. An alerts-only budget is a notification mechanism, not a hard spending cap. No budget amount has been selected or billing activated by this runbook.

References: [Geocoding billing and quotas](https://developers.google.com/maps/documentation/geocoding/usage-and-billing), [Places billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing), [Budget behavior](https://cloud.google.com/billing/docs/how-to/budgets).

## 4. Configure Google Auth Platform

1. Open **Google Auth Platform → Get Started** (or **Branding** if already initialized).
2. Set app name **Nyay Saathi**, the user support email, and developer contact email.
3. Select **External** audience for customers outside the owner's Workspace organization.
4. Under **Audience**, retain **Testing** during development and add the owner and approved testers.
5. Under **Branding**, supply the genuine application homepage, privacy policy, terms where applicable, and domains required by Google. Complete domain ownership verification if requested. Do not change the shared demo to achieve this; a separate product/policy site can be used.
6. Under **Data Access**, declare the scopes for the features actually being implemented. Request them incrementally in the app rather than all at first login.

| Permission | Purpose | Activation |
|---|---|---|
| `openid`, `email`, `profile` | Google account sign-in/identity when using that flow | Sign in |
| `https://www.googleapis.com/auth/drive.file` | Create/access app-created or explicitly selected/shared files | Customer selects Connect Drive |
| `https://www.googleapis.com/auth/gmail.send` | Send the specific customer-approved complaint | Customer enables sending |
| `https://www.googleapis.com/auth/gmail.readonly` | Import messages/read replies | Separate opt-in feature |
| `https://www.googleapis.com/auth/calendar.app.created` | Create an app-specific secondary calendar and manage its events | Optional Calendar connection; evaluate against implemented feature |

The updated Android onboarding target is Google-only sign-in, profile confirmation, optional connection cards, setup summary, then Home. Basic sign-in does not grant service permissions. Name/email/photo availability must be handled without assuming every field exists. Date of birth requires manual entry or a separate People API authorization and may still be unavailable. Calendar writes need approval of the exact event details, time zone and any attendees; connection alone does not authorize writes. See [shared checklist](../../checklist.md), [profile claims](https://developers.google.com/identity/openid-connect/openid-connect), [People API](https://developers.google.com/people/api/rest/v1/people/get) and [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth).

Preparing Gmail reading now is possible, but public activation requires the applicable restricted-scope verification and security assessment when restricted data passes through the backend. Gmail send is sensitive; Drive `drive.file` is non-sensitive. API enablement and declaring a scope do not themselves grant access to any customer's account.

References: [Consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent), [Gmail scope classifications](https://developers.google.com/workspace/gmail/api/auth/scopes), [Drive per-file access](https://developers.google.com/workspace/drive/api/guides/api-specific-auth).

## 5. Create OAuth clients

Open **Google Auth Platform → Clients → Create client**. OAuth clients are distinct from Maps API keys.

### Web client for Supabase Google sign-in

- Application type: **Web application**.
- Suggested name: `Nyay Saathi - Supabase Auth`.
- If using the standard Supabase Google OAuth flow, register this authorized redirect URI, checking it against the Google provider page in the correct Supabase dashboard:

```text
https://daojcrxjjkqoirqbvhjn.supabase.co/auth/v1/callback
```

- Add only browser origins actually used by this integration if required. Origins have no path component. Do not modify the existing Vercel deployment or environment.
- Put its client ID and client secret in the target Supabase project's Google provider settings. Never put the secret in `VITE_*` variables or the APK.
- In Supabase Auth URL configuration, allowlist the exact app return/deep-link URL implemented by the client. The current proposed app return is `in.nyaysaathi.app://oauth-callback`; agy must verify actual routing and cold-start behavior.

The Google HTTPS callback above and the application's final deep link serve different stages of the flow. Do not register the custom deep link as a Web client's Google HTTPS callback.

### Android client(s)

- Application type: **Android**.
- Package name: `in.nyaysaathi.app`.
- SHA-1: obtain from the certificate actually signing that build. Do not invent a value or use the Google Cloud project's hash.
- Agy should run the Android Gradle `signingReport` after the build toolchain is available. The usual command from `frontend/android` is `./gradlew signingReport`.
- Register the debug signing certificate for testing and the production app signing certificate for release. With Play App Signing, obtain the app signing certificate from Play Console's app integrity area; the upload certificate alone is not a substitute.

No existing debug keystore was found at the conventional owner path during this review, so no SHA-1 has been established here.

### Drive/Gmail authorization used by the backend

Agy must select and implement a supported authorization flow, separately from merely establishing a Supabase session. For Android, native Google authorization can request offline access and pass a one-time authorization code to the backend for exchange. Use the appropriate Web/server client ID in that flow. If implementing a browser-based backend OAuth flow instead, register that implemented HTTPS callback exactly; the Supabase Auth callback is not automatically a custom Google integration endpoint.

Do not fabricate callback URLs for routes that do not exist. Validate state/session binding and PKCE where applicable, verified account identity, granted scopes, and code exchange. Refresh/revoke customer tokens on the backend and bind connections to the authenticated owner.

References: [Create client credentials](https://developers.google.com/workspace/guides/create-credentials), [Supabase Google setup](https://supabase.com/docs/guides/auth/social-sign-in/auth-google), [Android Google data authorization](https://developer.android.com/identity/authorization).

## 6. Create Maps credentials with separate purposes

Under **APIs & Services → Credentials**, create API keys as needed. Apply API restrictions immediately.

| Suggested key | API restrictions | Where it belongs |
|---|---|---|
| `nyay-geocoding-server` | Geocoding API only | Backend secret |
| `nyay-places-server` | Places API (New) only | Backend secret |
| `nyay-maps-android` | Maps SDK for Android only, if used | Android configuration, restricted to package + signing SHA-1 |
| `nyay-maps-web` | Maps JavaScript API only, if used | Web client, with supported origin restrictions |

Do not reuse an Android-restricted key for backend REST calls. Do not expose either server key to the React bundle. For backend application restrictions, allowlist verified fixed outbound IP addresses only when the actual Edge deployment provides them. A Supabase project/database IP is not proof of an Edge Function's public egress IP. For dynamic egress, agy must document the supported authentication/proxy arrangement and compensating controls; do not claim an IP restriction is in place when it has not been verified. Evaluate supported server OAuth authentication where appropriate.

Keep the APIs behind authenticated, bounded application routes; do not expose an arbitrary Google URL proxy to customers or the model. The optional embedded-map credential depends on the actual native-vs-WebView implementation.

Reference: [Maps credential security and server restrictions](https://developers.google.com/maps/api-security-best-practices).

## 7. Location behavior and agent context

The proposed product flow is:

```text
Customer taps Use my location
→ Android asks for foreground location permission
→ App obtains a current coordinate with timestamp and accuracy
→ Authenticated backend requests reverse geocoding
→ App shows the suggested city/state and asks the customer to confirm/edit
→ Agent uses the confirmed region with the relevant case facts
```

- Ask for approximate, one-time foreground location sufficient for regional help. Add precise access only for a feature needing it. Background tracking is not required for the requested scope.
- Always offer manual state/city/district selection, including after denial, timeout, unavailable GPS, inaccurate results, border ambiguity, or travel.
- Keep current position separate from residence, incident location, transaction location, and any explicitly confirmed case region. Do not silently overwrite a case's region from GPS.
- Geocoding is a suggestion, not proof of a legal district or territorial jurisdiction. Administrative components may be missing or differ from official legal boundaries.
- Ask which region is relevant to the complaint when facts differ. Use an authoritative regional legal corpus and verified official contacts for substantive answers. Maps discovers places and helps navigation; a Places listing is not proof that an office is the correct authority or accepts that complaint.
- Send the agent the minimum relevant regional context. Avoid placing precise coordinates in prompts, generic logs, or persistent conversation memory unless that use is explicitly needed and disclosed.
- Treat Google Maps output as external data, not model instructions. Preserve provenance and distinguish a retrieved business/place listing from an independently verified official contact.
- Follow Google attribution, display, storage and caching requirements. Do not create a permanent address/place database from Google responses or copy complete responses into case memory. Keep only permitted identifiers and data within the applicable policy. User-entered case facts must retain their real source; relabeling provider data does not remove provider restrictions.
- Maps URLs can open navigation without enabling Routes API or embedding a map. Those URLs do not require an API key.

References: [Android location permissions](https://developer.android.com/develop/sensors-and-location/location/permissions), [Geocoding policies](https://developers.google.com/maps/documentation/geocoding/policies), [Maps URLs](https://developers.google.com/maps/documentation/urls/get-started).

## 8. Backend configuration contract for agy

The names below are proposals to implement, not environment variables already consumed by the current code:

```text
GOOGLE_OAUTH_WEB_CLIENT_ID=<server authorization client ID>
GOOGLE_OAUTH_WEB_CLIENT_SECRET=<backend secret>
GOOGLE_GEOCODING_API_KEY=<backend-only API-restricted key>
GOOGLE_PLACES_API_KEY=<backend-only API-restricted key>
```

Supabase Auth's provider credentials are configured in Auth settings, independently of any custom Edge authorization client. Do not assume setting one configures the other. Android client IDs and app-restricted map keys are client configuration, not shared server secrets. Continue encrypting per-customer Google tokens using properly provisioned server-side encryption keys; do not rely on a development fallback.

The reviewed Round 2 backend does not currently read the proposed Google/Maps environment variables or implement region resolution. Agy must implement and test these integrations. Do not deploy the currently reviewed false-success Gmail/Drive paths merely because credentials are available.

## 9. Completion checklist and evidence

- [ ] Project ID, project number, owner, and target Supabase project recorded.
- [ ] Requested APIs enabled; unused APIs left disabled.
- [ ] Maps billing linked by owner; budget amount and alerts chosen; actual quota settings recorded.
- [ ] Consent branding, External audience, test users, and selected scopes configured.
- [ ] Web/server and Android OAuth clients created; real debug/release SHA-1 values recorded.
- [ ] Correct callbacks and app return URLs configured for the implemented authorization paths.
- [ ] Secrets placed in the correct backend configuration and excluded from public builds/reports.
- [ ] Drive upload verified against a real file and original bytes in the customer's account.
- [ ] Approved Gmail send verified using an actual provider message ID and Sent-folder evidence.
- [ ] Token refresh, revocation, account mismatch, missing scopes, and ambiguous send tested.
- [ ] Optional Gmail reply monitoring tested and production verification/assessment completed as applicable.
- [ ] Foreground location on a real device tested, including denial, manual override, stale position and differing incident region.
- [ ] Reverse geocoding and Places tested with authenticated/rate-limited routes; error/quota fallback verified.
- [ ] Public launch branding, privacy disclosures, applicable Google OAuth verification and Play declarations completed.

Public verification and release signing cannot be declared complete from enabled APIs or mocked tests. Record provider receipts, device results, and any outstanding external review separately.
