# External API setup

All redirect URIs use `OAUTH_REDIRECT_BASE` (default `http://localhost:8000`).

## YouTube Data API v3 (required)
1. https://console.cloud.google.com → create a project → *APIs & Services → Library* → enable **YouTube Data API v3**.
2. *Credentials → Create credentials → API key*. Restrict it to YouTube Data API v3 → `YOUTUBE_API_KEY`.
3. Quota is 10,000 units per day by default. Costs: `videos.list` = 1 unit (one per stream per minute
   ≈ 1,440 a day), `search.list` = 100 units (only for `@handle/live` URLs, throttled to once per 5 min
   while offline), `liveChatMessages.list` ≈ 5 units per poll at the server-given interval. For several
   long streams a day, request a quota increase. On `quotaExceeded`, StreamPulse backs off and shows the
   error on the stream card. Prefer pasting `watch?v=` URLs to avoid search costs.

## YouTube uploads (Shorts)
1. Same project → *OAuth consent screen*: External, add yourself as a test user, add the scopes
   `youtube.upload` and `youtube.readonly`.
2. *Credentials → OAuth client ID → Web application*. Authorised redirect URI:
   `http://localhost:8000/api/accounts/youtube/callback` → `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
3. Dashboard → Accounts → YouTube Shorts → Connect.
4. Videos uploaded by **unverified** API projects are locked to private until the project passes Google's
   audit. StreamPulse defaults to `private`. Shorts are detected by YouTube for vertical videos ≤ 3 min,
   and `#Shorts` is appended to the description.

## Gemini
Create a key at https://aistudio.google.com/apikey → `GEMINI_API_KEY`, or Settings → AI (stored
encrypted). The model is configurable (`gemini-2.5-flash` by default). Prompts include only the
transcript, a chat sample, signal scores and up to 6 keyframes.

## TikTok
1. https://developers.tiktok.com → create an app, add **Login Kit** and **Content Posting API**
   (enable *Direct Post*). Scopes: `user.info.basic`, `video.publish`.
2. Redirect URI `http://localhost:8000/api/accounts/tiktok/callback`. Keys → `TIKTOK_CLIENT_KEY` / `TIKTOK_CLIENT_SECRET`.
3. **Until TikTok audits your app, every post is restricted to `SELF_ONLY` (private)** and the number of
   posting users is limited. StreamPulse reads the allowed privacy levels (`creator_info`) for every post
   and never tries to bypass them. Submit the app for audit to post publicly.
4. TikTok can also reject posts for its own daily caps (`spam_risk_too_many_posts`). Such jobs are
   rescheduled later.

## Instagram Reels
1. https://developers.facebook.com → create an app (type Business) → add **Instagram → API setup with
   Instagram login**. Permissions: `instagram_business_basic`, `instagram_business_content_publish`.
2. Add the redirect URI `http://localhost:8000/api/accounts/instagram/callback`. If Meta requires HTTPS
   redirect URIs for your app, use a local HTTPS reverse proxy (e.g. Caddy on `https://localhost`) and
   set `OAUTH_REDIRECT_BASE` accordingly. App ID/secret → `INSTAGRAM_APP_ID` / `INSTAGRAM_APP_SECRET`.
3. The Instagram account must be a **Business or Creator** account. While the app is in development mode,
   only accounts with a role on the app can connect. Advanced access requires App Review.
4. Uploads use the resumable `rupload.facebook.com` flow, so no public video URL is needed. The limit is
   50 API-published posts per 24 h, and StreamPulse checks `content_publishing_limit` before each upload.
5. Long-lived tokens last 60 days and are refreshed automatically before they expire.
