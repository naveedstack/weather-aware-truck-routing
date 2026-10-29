# Deploying

The runbook for putting this on Vercel. See [README.md](README.md) to run it locally.

## Vercel

The repository deploys as one Vercel project with two [services](https://vercel.com/docs/services),
set up in `vercel.json`: the Vite frontend (`frontend/`, served as static files) and the Django API
(`backend/`, one Python 3.14 function). Requests under `/api/` go to Django with their path
unchanged, and every other request goes to the frontend, so the browser calls the API on the same
origin, as it does locally through Vite's proxy. Vercel Services are in beta.

1. Push the repository to GitHub.
2. On vercel.com, choose **Add New… → Project** and import the repository.
3. Keep **Root Directory** at the repository root and set **Framework Preset** to **Services**.
   Leave the build settings alone: each service's build is set by its own folder (`package.json`,
   `requirements.txt` and `.python-version`).
4. Under **Environment Variables**, add these two for **Production** and **Preview**:
   - `DJANGO_SECRET_KEY`: a long random string, such as the output of
     `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`.
   - `TOMTOM_API_KEY`: your TomTom key.

   Add them before the first deploy: the build reads Django's settings and stops without the
   secret. Leave `DJANGO_DEBUG` unset.
5. Choose **Deploy**.
6. Check the deployment on the project's domain, the one listed under **Settings → Domains**
   (usually `https://<your-project>.vercel.app`), in a private browser window:
   `/api/health/` answers `{"status":"ok"}`, and the page plans a trip, for example
   Dallas, TX → Denver, CO.

Share that domain: it is the only public URL. Vercel puts its other URLs behind its login by default,
and a browser that is signed in to Vercel gets through, which is why the check above uses a private
window. Those are each deployment's own URL (`<project>-<hash>-<scope>.vercel.app`, the one the CLI
prints after "Production" and the dashboard links as the deployment) and the preview URLs of other
branches and pull requests. The CLI prints the public domain after "Aliased".

From then on, every push to the main branch deploys to production. The API runs in Vercel's default
region (`iad1`, Washington, D.C.) with the default 5-minute limit per request; a plan takes at most
about 20 seconds.

If something goes wrong:

- **The build fails with `DJANGO_SETTINGS_FAILED`** and "Set DJANGO_SECRET_KEY": the secret is
  missing for that environment. Add it and redeploy.
- **Planning says the TomTom key "may be missing, invalid or out of quota"**: set
  `TOMTOM_API_KEY` for that environment and redeploy. Changed variables only reach new
  deployments.
- **API requests answer `400 Bad Request` on a custom domain**: redeploy. `*.vercel.app` and the
  production domain (the shortest custom domain, if there is one) are allowed automatically, but the
  production domain is read when a deployment is built. Add any other custom domain (such as a
  `www.` one) to `DJANGO_ALLOWED_HOSTS`, then redeploy.

With the [Vercel CLI](https://vercel.com/docs/cli) instead of the dashboard, from the repository
root:

```bash
npm i -g vercel
vercel link                                    # creates or picks the project
vercel project update --framework services
vercel env add DJANGO_SECRET_KEY --environment production,preview --sensitive   # asks for the value
vercel env add TOMTOM_API_KEY --environment production,preview --sensitive
vercel deploy --prod
```

`.vercelignore` keeps `backend/.env` (and other local files) out of CLI uploads; Vercel's own list
of skipped files leaves `.env` in.

