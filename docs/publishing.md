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
    /etc/nginx/snippets/SITE.conf
sudo nginx -t && sudo systemctl reload nginx
```

`SITE.conf` stands for the host's shared site snippet, the one every virtual
host includes.

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

The raw-traces pipeline publishes each project's trace, stores, hash files,
PNGs and pages into the frames subtree of the archive (`frames_root` in
[`host.toml`](host-setup.md#hosttoml)). There is one upload: the archive's
normal five-minute upload carries the frames subtree with the clips and the
index (owner rulings BK and BO in the
[pipeline plan, Task 19](superpowers/plans/2026-11-26-raw-traces-pipeline.md#task-19-the-upload-split-decision-4-with-the-frames-upload-left-off)).
Nothing in this repository changes the upload.

- **Nothing is held back.** A project's frames reach the server within one
  upload interval of [`publish.py`](../ttvga/harness/publish.py) swapping them
  into the subtree.
- **Nothing is deleted on the server.** Removing or replacing a project
  locally does not unpublish its old files.
  [`tt-vga verify --server-stale URL`](../ttvga/harness/verify.py) lists what
  the server holds that the archive does not, for removal by hand.

### The cost: the upload's listing

Every run of the upload lists the whole archive, so the frames subtree
lengthens every run, whether or not anything changed. The pilot measured it
([measurements](reports/2026-11-pilot/measurements.md#the-uploads-listing-ruling-bk)):

| archive | files | listing (s) |
|---|---:|---:|
| before the frames subtree | 62,991 | 24 |
| with the pilot's 11 projects | 102,579 | 31 |
| projected: 408 projects, centre-v1 only | 547,544 | 107 |
| projected: 408 projects, both samplers | 1,094,642 | 189 |

The projection extrapolates about ten times past what was measured, so it is
checked as the files arrive.

### Logging the listing on every re-run

During every re-run that publishes frames, log each upload run's listing time
from the upload's log (read only), for example every 5 minutes:

```
uv run scripts/pilot_measure.py --upload-listing /var/lib/data-upload/rsync.log --last 5 >> tmp/upload-listing.log 2>&1
```

[`pilot_measure.py`](../scripts/pilot_measure.py) prints, per run, the file
count (`Number of files:`) and the time from `building file list` to
`total size is`.

If a listing comes near 4 minutes (240 s) of the 5-minute interval, stop
adding projects and take it to the owner (Ruling BO): runs would start to
overlap.
