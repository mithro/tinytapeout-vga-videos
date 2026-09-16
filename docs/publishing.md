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
