from typing import Any, Literal

from plotly.graph_objects import Figure

ElevationBackend = Literal["plotly", "tikzfigure", "matplotlib"]


def build_maxplotlib_elevation_canvas(
    traces: list[dict],
    *,
    height: int,
    width_to_height: float = 5.0,
    line_width: float = 1.5,
):
    from maxplotlib import Canvas

    figure_height = height / 100
    canvas, ax = Canvas.subplots(
        figsize=(figure_height * width_to_height, figure_height),
        fontsize=10,
    )
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
    return canvas


def build_maxplotlib_elevation_plot(
    traces: list[dict],
    *,
    height: int,
    backend: ElevationBackend = "plotly",
    width_to_height: float = 5.0,
    line_width: float = 1.5,
) -> Any:
    canvas = build_maxplotlib_elevation_canvas(
        traces,
        height=height,
        width_to_height=width_to_height,
        line_width=line_width,
    )

    if backend == "plotly":
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

    if backend == "tikzfigure":
        return canvas.plot(backend="tikzfigure")

    raise ValueError(f"Unsupported maxplotlib backend: {backend}")


def export_tikz_figure(
    fig,
    filepath: str,
    *,
    dpi: int = 200,
    transparent: bool = True,
    use_web_compilation: bool = False,
):
    print(f"Writing TikZ-backed figure to: {filepath}", flush=True)
    fig.savefig(
        filepath,
        dpi=dpi,
        transparent=transparent,
        use_web_compilation=use_web_compilation,
    )


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
