# Publishing the videos

The clips are written straight into the simulation user's `~/public_html`,
so the host can serve them without anything being copied twice:

```
/home/ttvga/public_html/index.html          the browsable index (tt-vga index --upload)
/home/ttvga/public_html/index.json          the same data, machine readable
/home/ttvga/public_html/<shuttle>/<macro>/  60s.avi, 30s.avi, 10s.avi, poster.png, contact.png
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
listings, and names the media types so browsers play the clips instead of
downloading them. Check it with:

```
curl -sI https://HOST/~ttvga/index.html
curl -sI https://HOST/~ttvga/tt08/tt_um_johshoff_metaballs/10s.avi
```

Both should answer `200` and the second should say
`Content-Type: video/x-msvideo`.

## Apache, for another host

```
sudo a2enmod userdir && sudo systemctl reload apache2
```

Apache's `userdir` module maps the same URLs to the same directory, so only
the permissions above are needed.
