from plotly.graph_objects import Figure


def export_plotly_fig(
    fig: Figure,
    filepath: str,
    config: dict,
    height: int = 200,
    width_to_height: float = 2.0,
    include_plotlyjs="cdn",
    full_html=False,
):
    ext = filepath.lower().split(".")[-1]

    if ext == "html":
        fig.write_html(
            filepath,
            include_plotlyjs=include_plotlyjs,
            full_html=full_html,
            config=config,
        )
    elif ext in {"png", "jpg", "jpeg", "pdf", "svg", "webp"}:
        fig.write_image(
            filepath,
            width=width_to_height * height,
            height=height,
            scale=1,
        )
    else:
        raise ValueError(f"Unsupported file extension '.{ext}'")
