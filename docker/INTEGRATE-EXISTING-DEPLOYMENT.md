# Integrate with an existing v16 Docker deployment

This is the preferred route for a working custom deployment. It does not require GitHub Actions. The exact Dockerfile/Compose changes depend on your existing build and will be prepared after inspecting them.

## Two stages in the same deployment workflow

**Image build:** include the app source, install its Python dependencies, register it in the image's app-code list and build its assets. All Frappe services must run the resulting same image. Keep every custom app you already use. If your build uses the official `frappe_docker` app list, add this app to that list alongside the existing v16 apps; the included `apps.example.json` is an example, not a replacement for your current list.

**Site initialization/migration:** after the site's persistent volumes, configuration and database are available, register the app on the existing site and migrate. This can be automated in your existing deploy/init job. A Docker image build cannot safely initialize the existing production database: the database belongs to the site, not to the image.

There is no need to manually enter the container and run `install-app`. The code includes a CLI-only, idempotent helper:

```text
revolut_bank_feed.deployment.ensure_installed
```

It uses Frappe's installer only if the app is missing, requires ERPNext v16 and checks that the image exposes the app through `apps.txt`. It is not a public API endpoint and never creates a new site. Already-installed sites return successfully, allowing normal migrations to handle upgrades.

`docker/deploy-site.sh` is a ready integration fragment for the deployment initializer. It selects only `REVOLUT_SITE`, invokes the helper and then migration. If your deployment already runs migration immediately afterwards, set `REVOLUT_RUN_MIGRATE=0`. Set `REVOLUT_ENABLE_SCHEDULER=1` only when this initializer should enable the site's scheduler; by default it preserves that setting.

Run the initializer as the normal `frappe` container user from the new image, with the same sites volume, network, database/Redis access and site configuration as the backend. Let your existing deployment handle backup, maintenance mode and worker draining before the initializer, and traffic/worker startup after success. Run exactly one initializer at a time for a site, and stop deployment if it fails. Do not put installation/migration in every backend or worker entrypoint.

The script assumes the standard `/home/frappe/frappe-bench` path; adapt it when your deployment uses a different path. Invoke it with `sh` so ZIP extraction does not need executable permissions. These instructions do not supply or modify your volumes, network, project name, services, image tags or secrets.

## What to share for an exact patch

- Your Docker build command and Dockerfile, including any build-stage/base-image references.
- Your Compose command and the referenced Compose file(s), especially configurator, backend, workers, scheduler and any existing migration/init service.
- Your existing app-list/build configuration, if any.
- Exact Frappe and ERPNext v16 release tags currently deployed, if known.

Redact passwords, access tokens and private keys. Keep variable names and service structure so they can be wired up correctly. Do not replace your current deployment with the generic example solely to add this app.

## After deployment

Open **`/desk/revolut-setup`** and follow the guided setup. The v16 app icon is also registered for System Managers. The scheduler and a worker consuming `long` are required. Credentials and account mappings stay in the site's encrypted database across container rebuilds.

The code targets Python 3.14.x and Frappe/ERPNext v16. Reuse compatible runtime/release choices from your existing v16 image; do not upgrade the entire stack just to follow a generic example. The supplied code has local tests and source-level compatibility checks; a live site migration and Docker build still need validation against your deployment.
