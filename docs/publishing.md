# Publishing the videos

The clips are written straight into the simulation user's `~/public_html`,
so the host can serve them without anything being copied twice:

```
/home/ttvga/public_html/index.html          the browsable index (tt-vga index --upload)
/home/ttvga/public_html/index.json          the same data, machine readable
/home/ttvga/public_html/<shuttle>/<macro>/  <shuttle>_<macro>_{60,30,10}s.{webm,mp4}
                                            <shuttle>_<macro>_{poster,contact}.png
                                            <shuttle>_<macro>_preview.gif
```

With a web server configured for user directories that is

<https://HOST/~ttvga/>

and the index's links are relative, so every clip is reachable from it.

## Permissions

The home directory must be traversable and the published tree readable by
the web server's user, and nothing else in the home may be exposed:

```
chmod o+x  /home/ttvga          # traverse only, the home itself stays unreadable
chmod -R o+rX /home/ttvga/public_html
```

`~/ttvga/` (the toolchain, the work directories, the source clones) keeps
its default permissions and is not reachable from the web.

## nginx

This host serves every virtual host from one shared snippet, so user
directories are added once, in their own snippet, and included there.
`ttvga/nginx/userdir-web.conf` in this repository is the file to install:

```
sudo install -m 644 -o root -g root ttvga/nginx/userdir-web.conf \
    /etc/nginx/snippets/userdir-web.conf
sudo sed -i '/include snippets\/sky130-mask-web.conf;/a include snippets\/userdir-web.conf;' \
    /etc/nginx/snippets/big-storage-site.conf
sudo nginx -t && sudo systemctl reload nginx
```

It maps `/~user/path` to `/home/user/public_html/path`, turns on directory
listings, and leaves the media types to nginx's own `/etc/nginx/mime.types`.

It deliberately has no `types` block. A `types` block in a location
*replaces* nginx's table rather than adding to it, so every extension it
did not list was served as `application/octet-stream` — and a browser will
not play a video or animate a GIF handed to it under that type. An earlier
version of this snippet made exactly that mistake with `.webm` and `.gif`.

Check it with:

```
curl -sI https://HOST/~ttvga/index.html
for f in 60s.mp4 60s.webm preview.gif poster.png; do
  curl -sI "https://HOST/~ttvga/tt08/tt_um_johshoff_metaballs/tt08_tt_um_johshoff_metaballs_$f" \
    | grep -i '^HTTP/\|^content-type'
done
```

Every one should answer `200`, and the types should read `video/mp4`,
`video/webm`, `image/gif` and `image/png`. An `application/octet-stream`
anywhere in that list means the `types` block is back.

## Apache, for another host

```
sudo a2enmod userdir && sudo systemctl reload apache2
```

Apache's `userdir` module maps the same URLs to the same directory, so only
the permissions above are needed.

## Mirroring onwards

The host may have a directory that is itself published somewhere else. On the
machine used so far, anything under `/srv/data.wafer.space` is rsynced to a
public server every five minutes.

`tt-vga mirror` copies the published tree into such a directory. Both sides
are on the host, so the copy runs there:

```
tt-vga mirror --host big --as-user tim --dest /srv/.../tinytapeout-vga-videos --dry-run
tt-vga mirror --host big --as-user tim --dest /srv/.../tinytapeout-vga-videos
```

`--as-user` exists because the destination usually belongs to whoever owns the
onward publishing rather than to the simulation user, which deliberately has no
privileges. Nothing about the destination is recorded in this repository.

Two things to know before running it.

It excludes the superseded `60s.avi`, `30s.avi` and `10s.avi` and the
unprefixed previews. Those are a capture format no browser will play, they are
218 GB, and they are removed by `tt-vga rerender --drop-legacy` anyway.

**Check what you are publishing first.** An onward sync of this kind is
typically append-only: deleting a file from the source does not unpublish the
copy already on the far server. Run `--dry-run`, and regenerate the index
(`tt-vga index --upload`) before mirroring, so the page being published points
at files that exist.

## Frames upload

The raw-traces pipeline publishes each project's trace, frames, PNGs and pages
into a frames subtree of the archive. That subtree will hold about 1.1 million
entries, against tens of thousands in the rest of the archive, so the archive's
onward upload is split in two:

- **The main upload** keeps its five-minute interval and excludes the frames
  subtree. It reads the subtree's path from a small root-owned configuration
  file and refuses to run if that file is missing or the path is not one plain
  relative path, so a lost configuration cannot publish the subtree by
  accident.
- **The frames upload** runs every 15 minutes and sends only the projects the
  pipeline has logged as changed. A second timer runs it weekly with `--full`,
  which sends the whole subtree and catches anything the incremental runs
  missed.

Neither ever deletes on the server. Removing a project locally does not
unpublish it.

Why two uploads: a longer interval for the one upload would delay the clips
too, and a separate slow upload that lists the whole subtree would still list
1.1 million entries on every run. The changed-project log keeps the clips at
five minutes and the frames upload's listing to the projects that changed.

The frames upload is installed before the pilot, with its timers **disabled**,
so that nothing in the subtree reaches the server until the full re-run has
been checked. Enabling the two timers is the act of publishing the frames.

### What the upload trusts

The pipeline runs as its own unprivileged user, and that user builds and runs
third-party Verilog. Each job runs inside a systemd scope, but the scope
confines **resources only** (memory, CPU, task count), not file access: a
hostile design can write anything the pipeline user can.

So the upload, which runs as the publishing account under the same sandboxing
as the main upload, trusts **nothing the pipeline user writes without
validating it**: neither the changed-project log nor anything in the frames
subtree. The frames upload:

- reads the log from the byte offset it stored last time, through the last
  complete line only. A partial last line waits for the next run. An offset
  past the end of the log (the log was shrunk) restarts at 0. The log must be a
  regular file, not a symlink, and is opened without blocking;
- accepts only lines matching `^[0-9T:+-]+ [A-Za-z0-9_]+/[A-Za-z0-9_]+$`
  (`<timestamp> <shuttle>/<project>`, as
  [`publish.py`](../ttvga/harness/publish.py) writes them). Every other line is
  logged and skipped;
- requires the frames subtree itself to be a real directory carrying the
  `.ttvga-frames-root` marker, with no symlink between the archive root and
  it;
- requires the shuttle and project directories to exist, not to be symlinks
  (`lstat`), and to have a `realpath` inside the subtree's `realpath`;
- refuses a project that contains any symlink (`find -P <project> -type l`,
  whose output is logged in full);
- builds every path it sends itself, and passes them to one `rsync` with the
  main upload's options plus `-r --files-from=- --safe-links
  --no-implied-dirs`.

After the transfer it runs the containment and symlink checks again on every
project it sent. A project that now fails is logged as
`realpath changed during transfer: <shuttle>/<project>`, for a person to look
at and, if need be, delete on the server by hand, and the run exits non-zero so
the journal shows it.

The stored offset moves on after rsync exits 0 or 23 (a partial transfer that
a retry would not fix). After 24 (files vanished, as when a project is
re-published mid-run) or any other failure it stays where it was, so those
projects are sent again on the next run. `--full` and dry runs never change it.
A lock keeps the 15-minute and weekly runs apart; a run that finds it held does
nothing.

### Residual risk

The checks run before rsync opens the paths. Between the check and the
transfer the pipeline user could swap a checked shuttle or project directory
for a symlink, and rsync would follow it while opening the path it was given.
`--safe-links` covers only symlinks *inside* the transferred directories, not
the path components leading to them. The window is short, the account that
could exploit it is the pipeline's own, and the post-transfer re-check
detects it after the fact (it cannot prevent it).

### The host files

[`host/data-upload/`](../host/data-upload/) holds the scripts, the
configuration file and the systemd units as they are installed, except that
every host-specific value (host and account names, absolute host paths) is a
`{{NAME}}` placeholder. [`render.py`](../host/data-upload/render.py) fills
them in from a private values file and refuses a placeholder without a value
or a value that is never used. The first commit of
[`data-upload-sync`](../host/data-upload/data-upload-sync) there is the live
script before this change, so its history is the reviewable diff.
[`tests/test_data_upload.py`](../tests/test_data_upload.py) renders the
templates into a sandbox and runs both scripts against a local directory
standing for the server.
