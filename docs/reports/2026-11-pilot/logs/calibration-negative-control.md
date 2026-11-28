<!-- Negative control for calibration.py: the calibration inputs copied, then grid's 000000.png replaced by bars' and prbs' 000011.png by its 000010.png. Exit 1. -->
| design | ui_in | mode | expected mode | size | frames | gaps | distinct | distinct equal to render | counter steps by 1 | result |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| tt_um_vgacal_bars | 0 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_grid | 0 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 1 | 0 | - | **differs** |
<!-- tt_um_vgacal_grid 000000.png: 302400 -->
| tt_um_vgacal_counter | 0 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 256 | 256 | yes | pixel-exact |
| tt_um_vgacal_prbs | 0 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 256 | 256 | **no** | **differs** |
| tt_um_vgacal_modes_m0 | 0 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m1 | 1 | 800x600@60 | 800x600@60 | 800x600 | 2,278 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m2 | 2 | 720x400@70 | 720x400@70 | 720x400 | 3,738 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m0_hneg | 4 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m0_vneg | 8 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
| tt_um_vgacal_modes_m0_hvneg | 12 | 640x480@60 | 640x480@60 | 640x480 | 3,596 | 0 | 1 | 1 | - | pixel-exact |
