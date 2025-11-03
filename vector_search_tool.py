"""
Vector Search Tool for ADK Agent
Provides easy interface for agents to query Barash clinical content
"""

from typing import Dict, Any, Optional, List
import sys
import os

# Add vectordb directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
vectordb_path = os.path.join(current_dir, 'vectordb')
if os.path.exists(vectordb_path) and vectordb_path not in sys.path:
    sys.path.insert(0, vectordb_path)

from vertex_vector_db_service import get_vertex_vector_db


class VectorSearchTool:
    """
    Tool for agents to search Barash Clinical Anesthesia content using vector search.
    """

    def __init__(self):
        """Initialize the vector search tool."""
        self.vector_db = get_vertex_vector_db()
        print("✅ Vector Search Tool initialized")

    def search(
        self,
        query: str,
        num_results: int = 5,
        section_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for relevant content.

        Args:
            query: The search query
            num_results: Number of results to return (default: 5)
            section_filter: Optional filter by section name

        Returns:
            Dictionary with search results
        """
        try:
            results = self.vector_db.query(
                query_text=query,
                n_results=num_results
            )

            # Apply section filter if specified
            if section_filter:
                filtered_docs = []
                filtered_metas = []
                filtered_dists = []
                filtered_ids = []

                for doc, meta, dist, doc_id in zip(
                    results['documents'],
                    results['metadatas'],
                    results['distances'],
                    results['ids']
                ):
                    if section_filter.lower() in meta.get('section', '').lower():
                        filtered_docs.append(doc)
                        filtered_metas.append(meta)
                        filtered_dists.append(dist)
                        filtered_ids.append(doc_id)

                results = {
                    'documents': filtered_docs,
                    'metadatas': filtered_metas,
                    'distances': filtered_dists,
                    'ids': filtered_ids
                }

            return {
                'success': True,
                'results': results,
                'num_results': len(results['documents'])
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'num_results': 0
            }

    def search_for_context(
        self,
        query: str,
        num_results: int = 5,
        section_filter: Optional[str] = None
    ) -> str:
        """
        Search and format results as context string for LLM.

        Args:
            query: The search query
            num_results: Number of results to return
            section_filter: Optional filter by section name

        Returns:
            Formatted context string
        """
        try:
            # First get raw results
            search_result = self.search(query, num_results, section_filter)

            if not search_result['success']:
                return f"Error searching: {search_result.get('error', 'Unknown error')}"

            if search_result['num_results'] == 0:
                return "No relevant content found."

            results = search_result['results']

            # Format as context
            context_parts = [
                f"# Relevant Content from Barash Clinical Anesthesia\n",
                f"Query: {query}\n",
                f"Found {len(results['documents'])} relevant sections:\n"
            ]

            for i, (doc, meta, dist) in enumerate(zip(
                results['documents'],
                results['metadatas'],
                results['distances']
            ), 1):
                section = meta.get('section', 'Unknown Section')
                topic = meta.get('topic', 'General')
                chunk_idx = meta.get('chunk_index', 0)

                context_parts.append(
                    f"\n{'='*70}\n"
                    f"[{i}] {section}\n"
                    f"Topic: {topic} | Chunk: {chunk_idx} | Relevance: {dist:.3f}\n"
                    f"{'='*70}\n\n"
                    f"{doc}\n"
                )

            return "\n".join(context_parts)

        except Exception as e:
            return f"Error formatting context: {str(e)}"

    def search_by_section(self, section_name: str, query: str, num_results: int = 3) -> str:
        """
        Search within a specific section.

        Args:
            section_name: Name of the section to search in
            query: The search query
            num_results: Number of results

        Returns:
            Formatted context string
        """
        return self.search_for_context(
            query=query,
            num_results=num_results,
            section_filter=section_name
        )

    def list_sections(self) -> List[str]:
        """
        Get list of available sections.

        Returns:
            List of section names
        """
        stats = self.vector_db.get_stats()
        # This would need to be enhanced to actually list sections from document cache
        return [
            "Section 1 - Introduction and Overview",
            "Section 2 - Basic Science and Fundamental's",
            "Section 3 - Cardiac Anatonomy and Physiology",
            "Section 4 - Anesthetic Drugs and Adjuvants",
            "Section 5 - Preoperative Assessment and Perioperative Monitoring",
            "Section 6 - Basic Anesthetic Managment",
            "Section 7 - Anesthesia Subspeciality Care",
            "Section 8 - Anesthesia for Selected Surgical Services",
            "Section 9 - Postanesthetic Managment, Critical Care, and Pain Managment"
        ]

    def get_stats(self) -> Dict[str, Any]:
        """
        Get vector database statistics.

        Returns:
            Dictionary with stats
        """
        return self.vector_db.get_stats()


# Function-based interface for ADK agents
def search_barash_content(
    query: str,
    num_results: int = 5,
    format_for_llm: bool = True
) -> str:
    """
    Simple function to search Barash content - designed for ADK agent tools.

    Args:
        query: What to search for
        num_results: Number of results to return
        format_for_llm: Whether to format results as context (vs raw JSON)

    Returns:
        Search results as formatted string or JSON

    Example:
        >>> context = search_barash_content("What are the effects of propofol on the cardiovascular system?")
        >>> print(context)
    """
    tool = VectorSearchTool()

    if format_for_llm:
        return tool.search_for_context(query, num_results)
    else:
        import json
        results = tool.search(query, num_results)
        return json.dumps(results, indent=2)


if __name__ == "__main__":
    # Test the tool
    print("="*80)
    print(" Vector Search Tool Test ")
    print("="*80)

    tool = VectorSearchTool()

    # Show stats
    stats = tool.get_stats()
    print("\n📊 Vector DB Stats:")
    print(f"   Total documents: {stats.get('total_documents', 0)}")

    # Test query
    print("\n🔍 Test Query: 'What are the cardiovascular effects of propofol?'")
    print("="*80)

    context = tool.search_for_context(
        query="What are the cardiovascular effects of propofol?",
        num_results=3
    )

    print(context)

    # Test section-specific search
    print("\n\n🔍 Section-Specific Search: Basic Science")
    print("="*80)

    section_context = tool.search_by_section(
        section_name="Section 2",
        query="pharmacokinetics",
        num_results=2
    )

    print(section_context)
