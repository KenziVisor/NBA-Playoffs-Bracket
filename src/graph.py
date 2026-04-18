import os
import tempfile
import webbrowser
from io import BytesIO
from itertools import combinations
from math import cos, pi, sin
from pathlib import Path


def _configure_matplotlib() -> None:
    import matplotlib

    matplotlib.use("Agg")


def build_results_graph(brackets):
    nodes = [bracket.name for bracket in brackets]
    edges = [
        (left.name, right.name, left.calculate_score(right))
        for left, right in combinations(brackets, 2)
    ]
    return nodes, edges


def build_positions(nodes):
    if not nodes:
        return {}
    if len(nodes) == 1:
        return {nodes[0]: (0.0, 0.0)}

    angle_step = 2 * pi / len(nodes)
    return {
        node: (cos(pi / 2 - index * angle_step), sin(pi / 2 - index * angle_step))
        for index, node in enumerate(nodes)
    }


def draw_results(axis, brackets) -> None:
    nodes, edges = build_results_graph(brackets)
    positions = build_positions(nodes)

    for left, right, weight in edges:
        left_x, left_y = positions[left]
        right_x, right_y = positions[right]
        axis.plot([left_x, right_x], [left_y, right_y], color="#7f8ea3", linewidth=1.2, zorder=1)
        axis.text(
            (left_x + right_x) / 2,
            (left_y + right_y) / 2,
            str(weight),
            ha="center",
            va="center",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": "none", "alpha": 0.9},
            zorder=3,
        )

    x_values = [positions[node][0] for node in nodes]
    y_values = [positions[node][1] for node in nodes]
    axis.scatter(x_values, y_values, s=700, c="#b9e6ff", edgecolors="#203247", linewidths=1.2, zorder=2)

    for node, (x_pos, y_pos) in positions.items():
        axis.text(x_pos, y_pos, node, ha="center", va="center", fontsize=10, zorder=4)

    axis.margins(0.25)
    axis.set_axis_off()


def render_results_image(brackets) -> bytes:
    _configure_matplotlib()
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(10, 7))
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    draw_results(axis, brackets)
    figure.tight_layout()

    buffer = BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    return buffer.getvalue()


def _write_temp_image(image_bytes: bytes) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png", prefix="bracket_scores_") as temp_file:
        temp_file.write(image_bytes)
        return Path(temp_file.name)


def _open_image(path: Path) -> None:
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.as_uri())
    except OSError:
        pass


def render_results(brackets) -> None:
    output_path = _write_temp_image(render_results_image(brackets))
    print(f"Saved graph image to {output_path}")
    _open_image(output_path)
