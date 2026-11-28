# Host facts, 2026-11-28

Read-only commands on the host, run 2026-11-28T11:44:30Z by the Task 22 fix round. Output is copied as printed, except where noted. Nothing was written to the host.

## Root volume: `df -B1 /`

| filesystem | 1B-blocks | used | available | use |
| --- | ---: | ---: | ---: | ---: |
| the root volume | 3,856,474,324,992 | 2,978,673,844,224 | 681,825,820,672 | 82% |

The device name is left out.

## Memory: `free -g`

| row | total | used | free | shared | buff/cache | available |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mem | 503 | 83 | 9 | 0 | 420 | 420 |
| Swap | 0 | 0 | 0 | - | - | - |

`free -g` prints GiB.

## Linger: `loginctl show-user ttvga -p Linger`

```
Linger=yes
```

## Timers

`ttvga`'s own (`sudo -n -u ttvga systemctl --user list-timers --all`, with its `XDG_RUNTIME_DIR`):

```
NEXT LEFT LAST PASSED UNIT ACTIVATES

0 timers listed.
```

The system's (`systemctl list-timers --all`): 23 timers listed. The upload's rows:

| unit | activates | last (UTC) | next (UTC) |
| --- | --- | --- | --- |
| `data-upload-wafer-space.timer` | `data-upload-wafer-space.service` | 2026-11-28T11:43:00Z | 2026-11-28T11:48:00Z |

The times are converted from the host's local time (UTC+10:30).

No `data-upload-wafer-space-frames` timer is installed. The other 22 rows are not copied, because several name other hosts; none is an upload timer.

## etckeeper

`sudo -n etckeeper vcs log --since=2026-11-25 --date=iso-strict --format='%h %ad %s'` (exit 0):

| commit | date | subject |
| --- | --- | --- |
| 5e80d1b | 2026-11-28T19:01:47+10:30 | letsencrypt: auto-commit changes |
| 7ec84a2 | 2026-11-28T00:19:57+10:30 | letsencrypt: auto-commit changes |
| 493457c | 2026-11-27T10:04:01+10:30 | letsencrypt: auto-commit changes |
| ee0cd96 | 2026-11-26T21:19:22+10:30 | letsencrypt: auto-commit changes |
| bbd607a | 2026-11-26T11:20:42+10:30 | letsencrypt: auto-commit changes |

`sudo -n etckeeper unclean`: exit 1, so `/etc` has no uncommitted change.

None of these commits comes from this pipeline.
