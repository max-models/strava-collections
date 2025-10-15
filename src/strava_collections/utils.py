def export_plotly_fig(fig, filepath, config, height=200, width_to_height=2.0):
    ext = filepath.lower().split(".")[-1]

    if ext == "html":
        fig.write_html(
            filepath,
            include_plotlyjs="cdn",
            full_html=True,
            config=config,
        )
    elif ext in {"png", "jpg", "jpeg", "pdf", "svg", "webp"}:
        fig.write_image(
            filepath, width=width_to_height * height, height=height, scale=1
        )
    else:
        raise ValueError(f"Unsupported file extension '.{ext}'")
