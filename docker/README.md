# Docker installation

Already have a working custom Docker deployment? Start with [Integrate an existing deployment](INTEGRATE-EXISTING-DEPLOYMENT.md). GitHub Actions is optional; keep your existing builder.

Use the official [frappe_docker](https://github.com/frappe/frappe_docker) deployment and a custom image. Docker Engine 23+ with BuildKit/buildx is required for the current secret-based app-list input. These are deployment instructions, not a claim that an image was built locally.

## Build from your GitHub repository

1. Publish this source tree to your GitHub organization. Commit your desired release and create a release tag. Do not publish credentials. Update `docker/apps.example.json` with the actual repository URL and tag/branch. Prefer a reviewed immutable tag for deployment.
2. Clone the official Docker repository, choose a reviewed commit, and copy the app list to `apps.json` inside it:

   ```bash
   git clone https://github.com/frappe/frappe_docker.git
   cd frappe_docker
   cp /absolute/path/to/revolut_bank_feed/docker/apps.example.json apps.json
   ```

   Edit `apps.json` before building. Keep ERPNext on version-16, and explicitly set Frappe to version-16 as below. For a repeatable release, select compatible tested v16 tags for both projects and record the Docker repository commit and resulting image digest.

3. Build using the current official `images/custom/Containerfile`:

   ```bash
   docker build \
     --build-arg FRAPPE_PATH=https://github.com/frappe/frappe \
     --build-arg FRAPPE_BRANCH=version-16 \
     --build-arg PYTHON_VERSION=3.14 \
     --build-arg NODE_VERSION=24 \
     --build-arg INSTALL_CHROMIUM=false \
     --secret id=apps_json,src=apps.json \
     --tag erpnext-revolut:16-0.4.0 \
     --file images/custom/Containerfile .
   ```

   The explicit Frappe v16, Python 3.14 and Node 24 choices make the target clear. Recheck its arguments when changing your pinned Docker commit. The first build downloads the Frappe/ERPNext toolchain and may take several minutes.

   `apps.json` is a BuildKit secret input. Do not use the older `APPS_JSON_BASE64` build-argument method, especially for private repository credentials. Base64 is not encryption. Prefer your organization's approved private-repository access method and short-lived build credentials.

4. Use the custom image for configurator, backend, frontend, websocket, scheduler, queue-short and queue-long. Either set `CUSTOM_IMAGE=erpnext-revolut`, `CUSTOM_TAG=16-0.4.0` and the appropriate `PULL_POLICY` in your existing environment file, or merge `compose.revolut.yaml` last:

   ```bash
   export REVOLUT_ERPNEXT_IMAGE=erpnext-revolut:16-0.4.0
   docker compose --env-file custom.env \
     -f compose.yaml \
     -f overrides/compose.mariadb.yaml \
     -f overrides/compose.redis.yaml \
     -f overrides/compose.noproxy.yaml \
     -f /absolute/path/to/revolut_bank_feed/docker/compose.revolut.yaml config
   ```

   This is an example using upstream MariaDB/Redis/no-proxy overrides; preserve your existing DB, network, volume, TLS and proxy setup. `compose.noproxy.yaml` does not provide production TLS—use your established HTTPS reverse proxy. Inspect the rendered configuration before deployment. Existing deployments must retain the same project name and volumes. Never run `down -v` for an upgrade.

5. With the **same Compose files, environment and project name** used for your deployment, back up before replacing containers. Then deploy the image with `up -d`. Install/migrate on the backend:

   ```bash
   docker compose exec backend bench --site erp.example.com backup --with-files
   docker compose exec backend bench --site erp.example.com install-app revolut_bank_feed
   docker compose exec backend bench --site erp.example.com migrate
   docker compose exec backend bench --site erp.example.com enable-scheduler
   docker compose restart backend scheduler queue-short queue-long websocket frontend
   ```

   These shorthand commands assume your shell/Compose configuration already selects the same deployment files and project. Add your normal `--env-file`, `-f` and `-p` arguments where needed. Asset build happens in the custom image; all services use that image. Frappe's configurator writes the installed-app code list into the shared sites volume.

6. Check the app and worker configuration:

   ```bash
   docker compose exec backend bench --site erp.example.com list-apps
   docker compose exec backend bench doctor
   docker compose logs --tail=100 scheduler queue-long
   ```

   The long worker must consume the `long` queue and allow a 900-second job. Persistent sites storage must include `site_config.json` and its `encryption_key`. Keep MariaDB and Redis private. Outbound HTTPS and DNS must work from backend and workers. Keep host/container clocks synchronized.

## Rebuild and upgrade

Disable connections and let active jobs finish. Back up. Build a new tag with the new app revision, deploy it to every Frappe service, run migration, then restart and re-enable. Do not run `bench update` inside an immutable container. If rolling back, restore a compatible database backup and its matching encryption key, not just an old image over an incompatible schema.

## Staging validation

Run [acceptance checks](../docs/acceptance.md), the bench integration tests, then a small Sandbox/live-statement comparison. No Revolut keys belong in Dockerfiles, Compose environment variables, the app-list file, CI logs, Git history or image layers. Configure them in the app's encrypted fields after site installation.
