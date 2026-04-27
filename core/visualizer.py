import networkx as nx
import matplotlib.pyplot as plt
from typing import Set

class GraphVisualizer:
    """
    Handles 2D visualization of subgraphs extracted during retrieval.
    """
    @staticmethod
    def plot_retrieval_subgraph(full_graph: nx.DiGraph, center_nodes: Set[str], context_nodes: Set[str]):
        """
        Generates a 2D Matplotlib figure of the retrieved subgraph.
        
        Args:
            full_graph (nx.DiGraph): The complete project dependency/call graph.
            center_nodes (Set[str]): Nodes that were direct semantic hits.
            context_nodes (Set[str]): The fully expanded set of nodes (centers + expanded).
            
        Returns:
            plt.Figure: The generated figure.
        """
        # Create subgraph (include only the nodes identified for context)
        valid_nodes = {n for n in context_nodes if n in full_graph}
        if not valid_nodes:
            fig, ax = plt.subplots(figsize=(12, 4))
            dark_bg = '#0b0e14' # Obsidian Floor Match
            ax.set_facecolor(dark_bg)
            fig.patch.set_facecolor(dark_bg)
            ax.text(0.5, 0.5, "NO_NODES_IN_PATH", color="#ffb59e", 
                    fontsize=14, fontfamily='monospace', ha='center', va='center', transform=ax.transAxes)
            ax.axis('off')
            return fig

        subgraph = full_graph.subgraph(valid_nodes).copy()
        
        # Filter edges: keep 'calls', 'contains', and 'semantic_link' for hierarchical display
        edges_to_remove = [
            (u, v) for u, v, d in subgraph.edges(data=True) 
            if d.get('edge_type') not in ('calls', 'contains', 'semantic_link')
        ]
        subgraph.remove_edges_from(edges_to_remove)

        # Use a force-directed layout for the 2D plane
        pos = nx.spring_layout(subgraph, seed=42, k=0.8)
        
        # Setup Figure Aesthetics
        fig, ax = plt.subplots(figsize=(12, 8))
        dark_bg = '#0b0e14'  # Obsidian Floor Match
        ax.set_facecolor(dark_bg)
        fig.patch.set_facecolor(dark_bg)

        # Setup node colors and sizes based on classification and historical usage
        node_colors = []
        node_sizes = []
        base_size = 1200
        
        for node in subgraph.nodes():
            node_data = subgraph.nodes[node]
            node_type = node_data.get('node_type', 'function')
            
            # Color
            if node_type == 'query':
                node_colors.append("#e2b4ff")  # VAULT Query (Anchor)
            elif node in center_nodes:
                node_colors.append("#ffb59e")  # VAULT Primary (Hit)
            elif node_type == 'class':
                node_colors.append("#bcc7de")  # VAULT Tertiary (Fixed)
            else:
                node_colors.append("#bdf4ff")  # VAULT Secondary (Neutral)
                
            # Size (Scaled by historical usage)
            usage = node_data.get("usage_count", 0)
            size_boost = 600 if node_type == 'query' else (400 if node_type == 'class' else 0)
            node_sizes.append(base_size + size_boost + (usage * 150))

        # Separate edge colors by type
        call_edges = [(u, v) for u, v, d in subgraph.edges(data=True) if d.get('edge_type') == 'calls']
        contain_edges = [(u, v) for u, v, d in subgraph.edges(data=True) if d.get('edge_type') == 'contains']

        # Separate nodes for different marker types
        query_nodes = [n for n in subgraph.nodes() if subgraph.nodes[n].get('node_type') == 'query']
        hit_nodes = [n for n in subgraph.nodes() if n in center_nodes and n not in query_nodes]
        ctx_nodes = [n for n in subgraph.nodes() if n not in center_nodes and n not in query_nodes]
        
        query_colors = [node_colors[i] for i, n in enumerate(subgraph.nodes()) if n in query_nodes]
        hit_colors = [node_colors[i] for i, n in enumerate(subgraph.nodes()) if n in hit_nodes]
        ctx_colors = [node_colors[i] for i, n in enumerate(subgraph.nodes()) if n in ctx_nodes]
        
        query_sizes = [node_sizes[i] for i, n in enumerate(subgraph.nodes()) if n in query_nodes]
        hit_sizes = [node_sizes[i] for i, n in enumerate(subgraph.nodes()) if n in hit_nodes]
        ctx_sizes = [node_sizes[i] for i, n in enumerate(subgraph.nodes()) if n in ctx_nodes]

        # Draw Nodes (Spheres/Circles for Hits)
        if hit_nodes:
            nx.draw_networkx_nodes(subgraph, pos, nodelist=hit_nodes, node_color=hit_colors, 
                                   node_size=hit_sizes, node_shape='o', ax=ax, alpha=0.9, 
                                   edgecolors="#ffb59e", linewidths=2)
        
        # Draw Nodes (Cubes/Squares for Context)
        if ctx_nodes:
            nx.draw_networkx_nodes(subgraph, pos, nodelist=ctx_nodes, node_color=ctx_colors, 
                                   node_size=ctx_sizes, node_shape='s', ax=ax, alpha=0.7,
                                   edgecolors="#00daf3", linewidths=1)
        
        # Draw call edges (solid, glowing orange)
        if call_edges:
            nx.draw_networkx_edges(
                subgraph, pos, edgelist=call_edges,
                edge_color="#ff571a", width=1.5, arrows=True,
                arrowstyle='-|>', arrowsize=20, alpha=0.8, ax=ax
            )
        
        # Draw contains edges (thin, cyan)
        if contain_edges:
            nx.draw_networkx_edges(
                subgraph, pos, edgelist=contain_edges,
                edge_color="#00daf3", width=1.2, arrows=True,
                arrowstyle='-|>', arrowsize=15, alpha=0.4, 
                style='dotted', ax=ax
            )

        # Draw semantic links (purple dashed)
        sem_link_edges = [(u, v) for u, v, d in subgraph.edges(data=True) if d.get('edge_type') == 'semantic_link']
        if sem_link_edges:
            nx.draw_networkx_edges(
                subgraph, pos, edgelist=sem_link_edges,
                edge_color="#e2b4ff", width=1.0, arrows=True,
                arrowstyle='-|>', arrowsize=10, alpha=0.5,
                style='dashed', ax=ax
            )
        
        # Draw Query Nodes (Stars for Anchors)
        if query_nodes:
            nx.draw_networkx_nodes(subgraph, pos, nodelist=query_nodes, node_color=query_colors,
                                   node_size=query_sizes, node_shape='*', ax=ax, alpha=1.0,
                                   edgecolors="#ffffff", linewidths=1)
        
        # Labels
        labels = {n: n.split("::")[-1] for n in subgraph.nodes()}
        nx.draw_networkx_labels(
            subgraph, pos, 
            labels, 
            font_size=9, 
            font_color="#e1e2eb", 
            font_family="monospace",
            font_weight='bold', 
            ax=ax
        )

        ax.set_title("VAULT_ENGINE // REASONING_MAP", color="#ffb59e", fontfamily='monospace', fontsize=12, pad=20)
        
        # Remove axes for a clean look
        ax.axis('off')
        plt.tight_layout()
        
        return fig

    @staticmethod
    def generate_3d_graph_html(full_graph: nx.DiGraph, center_nodes: Set[str], context_nodes: Set[str]) -> str:
        """
        Generates an interactive 3D WebGL graph using 3d-force-graph.
        """
        import json
        valid_nodes = {n for n in context_nodes if n in full_graph}
        if not valid_nodes: 
            return "<div style='color: #ffb59e; font-family: monospace; text-align: center; padding: 50px;'>NO_NODES_IN_WORKSPACE</div>"
        
        subgraph = full_graph.subgraph(valid_nodes).copy()
        
        # Filter edges: keep 'calls', 'contains', and 'semantic_link'
        edges_to_remove = [
            (u, v) for u, v, d in subgraph.edges(data=True) 
            if d.get('edge_type') not in ('calls', 'contains', 'semantic_link')
        ]
        subgraph.remove_edges_from(edges_to_remove)
        
        nodes_list = []
        for node in subgraph.nodes():
            node_data = subgraph.nodes[node]
            node_type = node_data.get('node_type', 'function')
            
            # Map style properties
            color = "#bdf4ff" # Default Context (Cyan)
            val = 5
            
            if node_type == 'query':
                color = "#e2b4ff" # Query (Purple)
                val = 20
            elif node in center_nodes:
                color = "#ffb59e" # Direct Hit (Coral)
                val = 10
            elif node_type == 'class':
                color = "#bcc7de" # Class (Slate)
                val = 8
            
            nodes_list.append({
                "id": node,
                "name": node.split("::")[-1],
                "color": color,
                "val": val
            })
            
        links_list = []
        for u, v, d in subgraph.edges(data=True):
            e_type = d.get('edge_type', 'calls')
            # calls=orange, contains=cyan, semantic=purple
            edge_color = "#ff571a" if e_type == 'calls' else ("#00daf3" if e_type == 'contains' else "#e2b4ff")
            links_list.append({
                "source": u,
                "target": v,
                "color": edge_color
            })
            
        graph_data_json = json.dumps({"nodes": nodes_list, "links": links_list})
        
        html_string = f"""
        <head>
          <style> 
            body {{ margin: 0; padding: 0; background-color: #0b0e14; overflow: hidden; height: 100vh; width: 100vw; }} 
            #3d-graph {{ width: 100%; height: 100%; }}
          </style>
          <script src="https://unpkg.com/3d-force-graph"></script>
        </head>
        <body>
          <div id="3d-graph"></div>
          <script>
            const Graph = ForceGraph3D()
              (document.getElementById('3d-graph'))
                .graphData({graph_data_json})
                .nodeLabel('name')
                .nodeColor(node => node.color)
                .nodeVal(node => node.val)
                .linkColor(link => link.color)
                .linkWidth(1.5)
                .linkDirectionalArrowLength(3.5)
                .linkDirectionalArrowRelPos(1)
                .backgroundColor('#0b0e14')
                .showNavInfo(false);
            
            // Handle Resizing
            window.addEventListener('resize', function() {{
                Graph.width(window.innerWidth);
                Graph.height(window.innerHeight);
            }});
          </script>
        </body>
        """
        return html_string
