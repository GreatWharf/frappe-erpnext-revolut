# Optional alternative: browser dashboard installation

ERPNext's own Desk cannot install server apps from a ZIP. This route uses **GitHub Actions for the image build**, and **an existing Portainer dashboard for deployment and its browser console for one-time site commands**. It needs no terminal on your computer, but it is not a one-click installation. If you do not have Portainer, use your existing server management system or the [Docker instructions](README.md); installing Portainer is a separate server task.

The supplied workflow targets Linux amd64 and a public GitHub source repository. Do not use it unchanged for an ARM server. Neither this workflow nor a Docker deployment was executed during authoring.

## 1. Create the image in GitHub

1. Extract the archive. Upload the **contents** of the `revolut_bank_feed` folder into a new public GitHub repository: `pyproject.toml` must be at the repository root. Include the hidden `.github` folder and all source files. Never upload credentials or site backups.
2. If your ERPNext deployment has other custom apps, add their public repository URLs and compatible tags to `docker/additional-apps.json`, using the same `url` / `branch` objects as `apps.example.json`. The image must contain every app already installed on the site.
3. Create a release tag for this source. Open **Actions → Build ERPNext image → Run workflow** and select that tag. Choose compatible Frappe and ERPNext v16 release tags matching your existing deployment. Defaults track version-16; use reviewed tags and a reviewed frappe_docker commit for repeatable builds. Do not accidentally downgrade either framework component.
4. Wait for success. The run summary displays the image name, such as `ghcr.io/your-org/your-repo:16-012345abcdef`. GitHub's default token builds and pushes the image; no Revolut secrets are involved.
5. In the repository's package settings, either make this code-only image public or configure GitHub Container Registry credentials in Portainer. Private source repositories need the private build method in the main Docker guide.

Official references: [GitHub image publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images), [Frappe Docker](https://github.com/frappe/frappe_docker).

## 2. Back up the current site

In Portainer, open the existing ERPNext **backend container → Console**, connect using `/bin/bash` as the normal `frappe` user, and run these lines after replacing `erp.example.com` with the actual site folder name:

```bash
cd /home/frappe/frappe-bench
bench --site erp.example.com backup --with-files
bench --site erp.example.com set-maintenance-mode on
```

Keep the backup off the server as well, including the site's encryption key. Pause existing feeds and allow active jobs to finish before replacing containers. Record the existing image, stack configuration and installed app list.

## 3. Deploy the new image

Open the **existing** ERPNext stack in Portainer. Change the Frappe image for **configurator, backend, frontend, websocket, scheduler, queue-short and queue-long** to the newly built image. Keep your database, Redis, network, proxy, volumes, environment and stack name unchanged. If your stack uses `CUSTOM_IMAGE` and `CUSTOM_TAG`, update those instead. Do not create a new ERPNext stack or delete volumes.

Use **Update the stack**, selecting the option to pull the image when available. For a Git-managed stack, edit its source repository and redeploy through Portainer. Verify the configurator completes and all Frappe services actually use the new image. Portainer's [stack editor guide](https://docs.portainer.io/user/docker/stacks/edit) explains these controls.

## 4. Install into the site from the browser console

Open the **new backend container → Console** as `frappe` and run:

```bash
cd /home/frappe/frappe-bench
bench --site erp.example.com install-app revolut_bank_feed
bench --site erp.example.com migrate
bench --site erp.example.com enable-scheduler
bench --site erp.example.com set-maintenance-mode off
bench --site erp.example.com list-apps
bench doctor
```

Run lines individually and stop on any error; leave maintenance mode on until resolved. For an upgrade of an already installed app, skip `install-app`. Restart backend, scheduler, both queue workers, websocket and frontend through Portainer. Confirm the long worker consumes `long`; the feed uses background jobs and cannot run using the web container alone.

Set the site's HTTPS `host_name` if needed using your existing configuration process. Open **`https://your-erp-site/desk/revolut-setup`** and follow the [browser setup guide](../docs/browser-setup.md).

Future image upgrades still use the hosting dashboard. Everyday connection setup, account mapping, sync and troubleshooting use ERPNext's frontend. Test on a staging copy first using the [acceptance checklist](../docs/acceptance.md).

For an existing custom build, use [the deployment integration guide](INTEGRATE-EXISTING-DEPLOYMENT.md) instead; this GitHub/Portainer route is not required.
