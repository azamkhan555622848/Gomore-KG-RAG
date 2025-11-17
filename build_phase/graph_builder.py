"""
Knowledge Graph Builder using NetworkX
Constructs graph from entities and relationships
"""

from typing import List, Dict, Tuple, Set
from collections import Counter, defaultdict
import networkx as nx
from loguru import logger
import community as community_louvain  # python-louvain

from shared.models import Entity, Relationship, TextChunk
from shared.config import get_build_config


class GraphBuilder:
    """Build knowledge graph from entities and relationships"""

    def __init__(self):
        self.config = get_build_config()
        self.graph = nx.MultiDiGraph()  # Directed graph with multiple edges
        self.entity_index: Dict[str, Entity] = {}
        self.chunk_index: Dict[str, TextChunk] = {}

        logger.info("GraphBuilder initialized")

    def add_entities(self, entities: List[Entity]) -> None:
        """
        Add entities as nodes to the graph

        Args:
            entities: List of Entity objects
        """
        logger.info(f"Adding {len(entities)} entities to graph")

        for entity in entities:
            # Add node with entity attributes
            self.graph.add_node(
                entity.entity_id,
                name=entity.name,
                type=entity.entity_type.value,
                mentions=entity.mentions,
                context=entity.context,
                chunk_ids=entity.chunk_ids,
                doc_ids=entity.doc_ids,
                mention_count=entity.mention_count,
                metadata=entity.metadata
            )

            # Add to index
            self.entity_index[entity.entity_id] = entity

        logger.info(f"Graph now has {self.graph.number_of_nodes()} nodes")

    def add_relationships(self, relationships: List[Relationship]) -> None:
        """
        Add relationships as edges to the graph

        Args:
            relationships: List of Relationship objects
        """
        logger.info(f"Adding {len(relationships)} relationships to graph")

        for rel in relationships:
            # Check if both entities exist
            if rel.source_entity_id not in self.graph or rel.target_entity_id not in self.graph:
                logger.warning(f"Skipping relationship with missing entities: {rel.relation_id}")
                continue

            # Add edge with relationship attributes
            self.graph.add_edge(
                rel.source_entity_id,
                rel.target_entity_id,
                key=rel.relation_id,
                relation_type=rel.relation_type.value,
                context=rel.context,
                chunk_id=rel.chunk_id,
                doc_id=rel.doc_id,
                confidence=rel.confidence,
                metadata=rel.metadata
            )

        logger.info(f"Graph now has {self.graph.number_of_edges()} edges")

    def add_chunks(self, chunks: List[TextChunk]) -> None:
        """
        Add chunks to index (for lookup)

        Args:
            chunks: List of TextChunk objects
        """
        for chunk in chunks:
            self.chunk_index[chunk.chunk_id] = chunk

        logger.info(f"Added {len(chunks)} chunks to index")

    def compute_centrality_scores(self) -> Dict[str, float]:
        """
        Compute PageRank centrality for all nodes

        Returns:
            Dict mapping entity_id to centrality score
        """
        logger.info("Computing PageRank centrality scores")

        try:
            # Convert to undirected for centrality calculation
            undirected = self.graph.to_undirected()

            # Compute PageRank
            centrality = nx.pagerank(undirected, alpha=0.85, max_iter=100)

            # Update node attributes
            nx.set_node_attributes(self.graph, centrality, 'centrality')

            logger.info("Centrality scores computed")
            return centrality

        except Exception as e:
            logger.error(f"Error computing centrality: {e}")
            return {}

    def detect_communities(self) -> Dict[str, int]:
        """
        Detect communities using Louvain algorithm

        Returns:
            Dict mapping entity_id to community_id
        """
        logger.info("Detecting communities using Louvain algorithm")

        try:
            # Convert to undirected for community detection
            undirected = self.graph.to_undirected()

            # Detect communities
            communities = community_louvain.best_partition(undirected)

            # Update node attributes
            nx.set_node_attributes(self.graph, communities, 'community')

            num_communities = len(set(communities.values()))
            logger.info(f"Detected {num_communities} communities")

            return communities

        except Exception as e:
            logger.error(f"Error detecting communities: {e}")
            return {}

    def get_statistics(self) -> Dict:
        """
        Get graph statistics

        Returns:
            Dictionary of statistics
        """
        num_nodes = self.graph.number_of_nodes()
        num_edges = self.graph.number_of_edges()

        # Entity type distribution
        entity_types = Counter()
        for node, data in self.graph.nodes(data=True):
            entity_types[data.get('type', 'UNKNOWN')] += 1

        # Relation type distribution
        relation_types = Counter()
        for u, v, data in self.graph.edges(data=True):
            relation_types[data.get('relation_type', 'UNKNOWN')] += 1

        # Degree statistics
        degrees = [self.graph.degree(node) for node in self.graph.nodes()]
        avg_degree = sum(degrees) / len(degrees) if degrees else 0

        # Get top entities by degree
        top_entities_by_degree = sorted(
            [(node, self.graph.degree(node), self.graph.nodes[node].get('name', 'Unknown'))
             for node in self.graph.nodes()],
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Get top entities by centrality (if computed)
        top_entities_by_centrality = []
        if any('centrality' in data for node, data in self.graph.nodes(data=True)):
            top_entities_by_centrality = sorted(
                [(node, data.get('centrality', 0), data.get('name', 'Unknown'))
                 for node, data in self.graph.nodes(data=True)],
                key=lambda x: x[1],
                reverse=True
            )[:10]

        stats = {
            'num_nodes': num_nodes,
            'num_edges': num_edges,
            'density': nx.density(self.graph) if num_nodes > 0 else 0,
            'avg_degree': avg_degree,
            'entity_type_distribution': dict(entity_types),
            'relation_type_distribution': dict(relation_types),
            'top_entities_by_degree': [
                {'entity_id': e[0], 'name': e[2], 'degree': e[1]}
                for e in top_entities_by_degree
            ],
            'top_entities_by_centrality': [
                {'entity_id': e[0], 'name': e[2], 'centrality': e[1]}
                for e in top_entities_by_centrality
            ]
        }

        return stats

    def get_entity_neighborhood(
        self,
        entity_id: str,
        hops: int = 1,
        max_neighbors: int = 50
    ) -> Tuple[Set[str], Set[Tuple[str, str]]]:
        """
        Get K-hop neighborhood of an entity

        Args:
            entity_id: Entity ID
            hops: Number of hops
            max_neighbors: Maximum neighbors to return

        Returns:
            Tuple of (neighbor_entity_ids, edge_tuples)
        """
        if entity_id not in self.graph:
            return set(), set()

        # BFS to find K-hop neighbors
        neighbors = set([entity_id])
        edges = set()

        current_level = {entity_id}

        for hop in range(hops):
            next_level = set()

            for node in current_level:
                # Get successors (outgoing edges)
                for successor in self.graph.successors(node):
                    if successor not in neighbors:
                        next_level.add(successor)
                        edges.add((node, successor))

                # Get predecessors (incoming edges)
                for predecessor in self.graph.predecessors(node):
                    if predecessor not in neighbors:
                        next_level.add(predecessor)
                        edges.add((predecessor, node))

            neighbors.update(next_level)
            current_level = next_level

            # Check limit
            if len(neighbors) >= max_neighbors:
                break

        # Limit to max_neighbors
        if len(neighbors) > max_neighbors:
            # Keep highest degree neighbors
            neighbor_degrees = [
                (n, self.graph.degree(n)) for n in neighbors if n != entity_id
            ]
            neighbor_degrees.sort(key=lambda x: x[1], reverse=True)
            neighbors = {entity_id} | {n for n, _ in neighbor_degrees[:max_neighbors-1]}

            # Filter edges
            edges = {e for e in edges if e[0] in neighbors and e[1] in neighbors}

        return neighbors, edges

    def get_entity_by_name(self, name: str) -> List[Entity]:
        """
        Find entities by name

        Args:
            name: Entity name

        Returns:
            List of matching entities
        """
        name_lower = name.lower()
        matching = []

        for entity in self.entity_index.values():
            if name_lower in entity.name.lower():
                matching.append(entity)
            elif any(name_lower in mention.lower() for mention in entity.mentions):
                matching.append(entity)

        return matching

    def get_connecting_path(
        self,
        source_id: str,
        target_id: str,
        max_length: int = 3
    ) -> List[List[str]]:
        """
        Find shortest paths between two entities

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            max_length: Maximum path length

        Returns:
            List of paths (each path is a list of entity IDs)
        """
        if source_id not in self.graph or target_id not in self.graph:
            return []

        try:
            # Convert to undirected for path finding
            undirected = self.graph.to_undirected()

            # Find all simple paths up to max_length
            paths = list(nx.all_simple_paths(
                undirected,
                source_id,
                target_id,
                cutoff=max_length
            ))

            return paths[:5]  # Return top 5 paths

        except nx.NetworkXNoPath:
            return []
        except Exception as e:
            logger.error(f"Error finding paths: {e}")
            return []

    def export_graph(self) -> nx.MultiDiGraph:
        """
        Export the NetworkX graph

        Returns:
            NetworkX MultiDiGraph
        """
        return self.graph

    def get_graph_summary(self) -> str:
        """
        Get a text summary of the graph

        Returns:
            Summary string
        """
        stats = self.get_statistics()

        summary = f"""
Knowledge Graph Summary
=======================
Nodes: {stats['num_nodes']}
Edges: {stats['num_edges']}
Density: {stats['density']:.4f}
Average Degree: {stats['avg_degree']:.2f}

Entity Types:
{self._format_distribution(stats['entity_type_distribution'])}

Relation Types:
{self._format_distribution(stats['relation_type_distribution'])}

Top Entities (by degree):
{self._format_top_entities(stats['top_entities_by_degree'][:5])}
"""

        return summary.strip()

    def _format_distribution(self, dist: Dict) -> str:
        """Format distribution as string"""
        lines = []
        for key, count in sorted(dist.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {key}: {count}")
        return "\n".join(lines) if lines else "  (none)"

    def _format_top_entities(self, entities: List[Dict]) -> str:
        """Format top entities as string"""
        lines = []
        for i, e in enumerate(entities, 1):
            lines.append(f"  {i}. {e['name']} (degree: {e.get('degree', 0)})")
        return "\n".join(lines) if lines else "  (none)"


if __name__ == "__main__":
    # Test the graph builder
    from shared.utils import setup_logging
    from shared.models import EntityType, RelationType

    setup_logging(level="INFO")

    # Create sample entities
    entities = [
        Entity(
            entity_id="ent_001",
            name="Jane Smith",
            entity_type=EntityType.PERSON,
            mentions=["Jane Smith", "Dr. Smith"],
            chunk_ids=["chunk_001"],
            doc_ids=["doc_001"],
            mention_count=2
        ),
        Entity(
            entity_id="ent_002",
            name="Google",
            entity_type=EntityType.ORGANIZATION,
            mentions=["Google"],
            chunk_ids=["chunk_001"],
            doc_ids=["doc_001"],
            mention_count=1
        ),
        Entity(
            entity_id="ent_003",
            name="Mountain View",
            entity_type=EntityType.LOCATION,
            mentions=["Mountain View"],
            chunk_ids=["chunk_001"],
            doc_ids=["doc_001"],
            mention_count=1
        )
    ]

    # Create sample relationships
    relationships = [
        Relationship(
            relation_id="rel_001",
            source_entity_id="ent_001",
            target_entity_id="ent_002",
            relation_type=RelationType.WORKS_FOR,
            chunk_id="chunk_001",
            doc_id="doc_001"
        ),
        Relationship(
            relation_id="rel_002",
            source_entity_id="ent_002",
            target_entity_id="ent_003",
            relation_type=RelationType.LOCATED_IN,
            chunk_id="chunk_001",
            doc_id="doc_001"
        )
    ]

    # Build graph
    builder = GraphBuilder()
    builder.add_entities(entities)
    builder.add_relationships(relationships)

    # Get statistics
    stats = builder.get_statistics()

    print(builder.get_graph_summary())
