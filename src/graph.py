from io import BytesIO
from itertools import combinations

import networkx as nx


def build_results_graph(brackets):
    graph = nx.Graph()
    graph.add_nodes_from([bracket.name for bracket in brackets])

    for left, right in combinations(brackets, 2):
        graph.add_edge(left.name, right.name, weight=left.calculate_score(right))

    return graph


def draw_results(axis, brackets) -> None:
    graph = build_results_graph(brackets)
    positions = nx.spring_layout(graph)
    nx.draw_networkx_nodes(graph, positions, node_color="lightblue", node_size=700, ax=axis)
    nx.draw_networkx_edges(graph, positions, ax=axis)
    nx.draw_networkx_labels(graph, positions, ax=axis)
    edge_labels = nx.get_edge_attributes(graph, "weight")
    nx.draw_networkx_edge_labels(graph, positions, edge_labels=edge_labels, ax=axis)
    axis.set_axis_off()


def render_results_image(brackets) -> bytes:
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


def render_results(brackets) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(10, 7))
    draw_results(axis, brackets)
    figure.tight_layout()
    plt.show()
