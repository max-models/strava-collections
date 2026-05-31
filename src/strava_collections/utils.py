from plotly.graph_objects import Figure


def build_maxplotlib_elevation_fig(
    traces: list[dict],
    *,
    height: int,
    line_width: float = 1.5,
) -> Figure:
    from maxplotlib import Canvas

    canvas, ax = Canvas.subplots(figsize=(6, height / 100), fontsize=10)
    for trace in traces:
        color = trace.get("color", "black")
        ax.fill_between(trace["x"], trace["y"], 0, color=color, alpha=0.15)
        ax.plot(
            trace["x"],
            trace["y"],
            color=color,
            linewidth=trace.get("line_width", line_width),
        )

    ax.set_xlabel("Distance (km)")
    ax.set_ylabel("Elevation (m)")
    ax.set_grid(False)

    fig = canvas.plot(backend="plotly")
    fig.update_layout(
        height=height,
        hovermode="x unified",
        showlegend=False,
        xaxis=dict(tickformat=",.0f"),
        margin=dict(l=0, r=0, t=0, b=0),
        autosize=True,
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_traces(
        hovertemplate="Distance: %{x:.1f} km<br>Elevation: %{y:.1f} m<extra></extra>",
        selector=dict(type="scatter"),
    )
    return fig


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
        print(f"Writing Plotly HTML to: {filepath}", flush=True)
        fig.write_html(
            filepath,
            include_plotlyjs=include_plotlyjs,
            full_html=full_html,
            config=config,
        )
    elif ext in {"png", "jpg", "jpeg", "pdf", "svg", "webp"}:
        print(f"Writing Plotly image to: {filepath}", flush=True)
        fig.write_image(
            filepath,
            width=width_to_height * height,
            height=height,
            scale=1,
        )
    else:
        raise ValueError(f"Unsupported file extension '.{ext}'")
