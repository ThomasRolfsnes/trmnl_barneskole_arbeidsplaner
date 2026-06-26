"""TRMNL device render profiles (pixel dimensions + grayscale)."""

DEVICES = {
    # TRMNL X — 10.3", 1872x1404, 16-level grayscale. The weekly plans are A4
    # landscape, so the device's native landscape orientation is the best fit.
    "trmnl_x_landscape": {"width": 1872, "height": 1404, "grayscale": True},
    "trmnl_x_portrait": {"width": 1404, "height": 1872, "grayscale": True},
    # Original TRMNL / 7.5" — 800x480, 1-bit.
    "trmnl_og": {"width": 800, "height": 480, "grayscale": True},
}
