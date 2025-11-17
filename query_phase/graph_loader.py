"""
Graph Loader for Query Phase
Efficiently loads pre-built knowledge graph for mobile deployment
"""

import json
import gzip
from pathlib import Path
from typing import Dict, Optional
import numpy as np
import networkx as nx
from loguru import logger

from shared.models import Entity, TextChunk, GraphExportMetadata
from shared.config import get_shared_config, get_query_config


class GraphLoader:
    """Load and manage knowledge graph for querying"""

    def __init__(self):
        self.shared_config = get_shared_config()
        self.query_config = get_query_config()

        self.graph: Optional[nx.MultiDiGraph] = None
        self.entity_index: Dict[str, Dict] = {}
        self.chunk_index: Dict[str, Dict] = {}
        self.metadata: Optional[GraphExportMetadata] = None

        logger.info("GraphLoader initialized")

    def load_graph(self, graph_path: Path = None) -> nx.MultiDiGraph:
        """
        Load knowledge graph from file

        Args:
            graph_path: Optional custom path (defaults to config path)

        Returns:
            NetworkX graph
        """
        if graph_path is None:
            graph_path = self.shared_config.graph_path

        logger.info(f"Loading graph from {graph_path}")

        # Load graph
        if graph_path.suffix == '.gz':
            with gzip.open(graph_path, 'rt', encoding='utf-8') as f:
                graph_data = json.load(f)
        else:
            with open(graph_path, 'r', encoding='utf-8') as f:
                graph_data = json.load(f)

        # Convert to NetworkX graph
        self.graph = nx.node_link_graph(graph_data, directed=True, multigraph=True)

        logger.info(f"Graph loaded: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

        # Build indexes
        self._build_indexes()

        return self.graph

    def load_metadata(self, metadata_path: Path = None) -> GraphExportMetadata:
        """
        Load export metadata

        Args:
            metadata_path: Optional custom path

        Returns:
            GraphExportMetadata
        """
        if metadata_path is None:
            metadata_path = self.shared_config.metadata_path

        logger.info(f"Loading metadata from {metadata_path}")

        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata_dict = json.load(f)

        self.metadata = GraphExportMetadata(**metadata_dict)

        logger.info(f"Metadata loaded: {self.metadata.num_entities} entities, {self.metadata.num_chunks} chunks")

        return self.metadata

    def _build_indexes(self) -> None:
        """Build entity and chunk indexes for fast lookup"""
        logger.info("Building indexes")

        # Build entity index (entity_id -> node data)
        for node, data in self.graph.nodes(data=True):
            self.entity_index[node] = data

        logger.info(f"Entity index built: {len(self.entity_index)} entities")

    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """
        Get entity by ID

        Args:
            entity_id: Entity ID

        Returns:
            Entity data dict or None
        """
        return self.entity_index.get(entity_id)

    def get_entity_by_name(self, name: str) -> list:
        """
        Find entities by name

        Args:
            name: Entity name (partial match)

        Returns:
            List of matching entity IDs
        """
        name_lower = name.lower()
        matching = []

        for entity_id, data in self.entity_index.items():
            entity_name = data.get('name', '').lower()

            if name_lower in entity_name:
                matching.append(entity_id)
            elif 'mentions' in data:
                mentions = data['mentions']
                if any(name_lower in mention.lower() for mention in mentions):
                    matching.append(entity_id)

        return matching

    def get_neighbors(self, entity_id: str, hops: int = 1) -> set:
        """
        Get K-hop neighbors of an entity

        Args:
            entity_id: Entity ID
            hops: Number of hops

        Returns:
            Set of neighbor entity IDs
        """
        if not self.graph or entity_id not in self.graph:
            return set()

        neighbors = set([entity_id])
        current_level = {entity_id}

        for _ in range(hops):
            next_level = set()

            for node in current_level:
                # Get successors and predecessors
                next_level.update(self.graph.successors(node))
                next_level.update(self.graph.predecessors(node))

            neighbors.update(next_level)
            current_level = next_level

        return neighbors

    def get_relationships(self, entity_id: str) -> list:
        """
        Get all relationships for an entity

        Args:
            entity_id: Entity ID

        Returns:
            List of (source, target, relation_type) tuples
        """
        if not self.graph or entity_id not in self.graph:
            return []

        relationships = []

        # Outgoing edges
        for target in self.graph.successors(entity_id):
            edges = self.graph[entity_id][target]
            for key, data in edges.items():
                relationships.append((
                    entity_id,
                    target,
                    data.get('relation_type', 'UNKNOWN')
                ))

        # Incoming edges
        for source in self.graph.predecessors(entity_id):
            edges = self.graph[source][entity_id]
            for key, data in edges.items():
                relationships.append((
                    source,
                    entity_id,
                    data.get('relation_type', 'UNKNOWN')
                ))

        return relationships

    def get_entity_context(self, entity_id: str, max_hops: int = 2) -> Dict:
        """
        Get context around an entity (neighbors + relationships)

        Args:
            entity_id: Entity ID
            max_hops: Maximum hops for neighborhood

        Returns:
            Dict with entity context
        """
        if not self.graph or entity_id not in self.graph:
            return {}

        # Get entity data
        entity_data = self.get_entity(entity_id)

        # Get neighbors
        neighbors = self.get_neighbors(entity_id, hops=max_hops)

        # Get relationships
        relationships = self.get_relationships(entity_id)

        return {
            'entity_id': entity_id,
            'entity_data': entity_data,
            'neighbors': list(neighbors),
            'relationships': relationships,
            'num_neighbors': len(neighbors),
            'num_relationships': len(relationships)
        }

    def is_loaded(self) -> bool:
        """Check if graph is loaded"""
        return self.graph is not None


if __name__ == "__main__":
    # Test the graph loader
    from shared.utils import setup_logging

    setup_logging(level="INFO")

    loader = GraphLoader()

    # Check if graph file exists
    if loader.shared_config.graph_path.exists():
        # Load graph
        graph = loader.load_graph()

        print(f"\nGraph loaded successfully")
        print(f"  Nodes: {graph.number_of_nodes()}")
        print(f"  Edges: {graph.number_of_edges()}")

        # Load metadata
        if loader.shared_config.metadata_path.exists():
            metadata = loader.load_metadata()
            print(f"\nMetadata:")
            print(f"  Documents: {metadata.num_documents}")
            print(f"  Chunks: {metadata.num_chunks}")
            print(f"  Entities: {metadata.num_entities}")

        # Test entity lookup
        if graph.number_of_nodes() > 0:
            sample_entity_id = list(graph.nodes())[0]
            context = loader.get_entity_context(sample_entity_id)

            print(f"\nSample entity: {sample_entity_id}")
            print(f"  Name: {context['entity_data'].get('name', 'N/A')}")
            print(f"  Type: {context['entity_data'].get('type', 'N/A')}")
            print(f"  Neighbors: {context['num_neighbors']}")
            print(f"  Relationships: {context['num_relationships']}")
    else:
        print(f"Graph file not found: {loader.shared_config.graph_path}")
        print("Please run the build phase first to create the knowledge graph")
