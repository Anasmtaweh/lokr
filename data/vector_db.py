import chromadb
import shutil
import os
from pathlib import Path
from typing import Dict, Any, List

class CodebaseVectorDB:
    """
    Semantic search engine utilizing ChromaDB.
    Indexes parsed generic AST elements (Classes, Functions, Docstrings) 
    into a persistent local vector store for neural retrieval.
    Includes a Self-Healing mechanism for metadata corruption recovery.
    """

    def __init__(self, db_dir: str | Path = "data/vector_store") -> None:
        """
        Initializes the ChromaDB persistent client pointing to the local directory,
        and ensures the required AST collection exists.
        
        Self-healing: If the collection or client initialization fails due to 
        metadata corruption (e.g. missing UUID folders), it wipes the store and restarts.
        """
        self.db_path = Path(db_dir).resolve()
        
        try:
            self._bootstrap_client()
        except Exception as e:
            # If initialization fails (e.g. Collection not found or index mismatch)
            # we perform a HARD RESET of the physical storage.
            print(f"[!] Intelligence Store Corruption Detected: {e}")
            self._hard_reset_storage()
            self._bootstrap_client()

    def _bootstrap_client(self) -> None:
        """Helper to initialize client and collection."""
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        # This is where the 'Collection does not exist' usually triggers if metadata is stale
        self.collection = self.client.get_or_create_collection(name="codebase_ast")

    def _hard_reset_storage(self) -> None:
        """Force-wipes the vector store directory to clear corrupted metadata."""
        print("[*] Performing Hard Reset on Vector Store...")
        if self.db_path.exists():
            # Delete all subdirectories (UUID folders) and files (sqlite)
            for item in self.db_path.iterdir():
                if item.name == ".gitkeep":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        else:
            self.db_path.mkdir(parents=True, exist_ok=True)

    def reset_collection(self) -> None:
        """
        Drops and recreates the collection, clearing all stale data.
        Essential when re-indexing a different project.
        """
        try:
            self.client.delete_collection(name="codebase_ast")
        except Exception:
            # Handle cases where collection doesn't exist yet
            pass
        self.collection = self.client.get_or_create_collection(name="codebase_ast")

    def upsert_nodes(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]) -> None:
        """
        Upserts multiple nodes into the Chroma collection.
        
        Args:
            documents (List[str]): Text representations of the nodes.
            metadatas (List[Dict[str, Any]]): Metadata for each node.
            ids (List[str]): Unique IDs for each node.
        """
        if not ids:
            return
            
        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

    def delete_nodes(self, ids: List[str]) -> None:
        """
        Removes nodes from the collection by their IDs.
        
        Args:
            ids (List[str]): List of node IDs to remove.
        """
        if not ids:
            return
            
        try:
            self.collection.delete(ids=ids)
        except Exception as e:
            # Chromadb might raise an error if IDs don't exist
            pass

    def delete_file(self, filepath: Path) -> None:
        """
        @deprecated Use delete_nodes instead. This remains for back-compat during transition.
        """
        doc_id = str(filepath.resolve())
        self.delete_nodes([doc_id])

    def search(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Performs semantic vector-search across the entire codebase index 
        returning the closest parsed document representations.

        Args:
            query (str): The natural language embedding search term.
            n_results (int): Max number of items to pull from the DB.

        Returns:
            List[Dict[str, Any]]: Packed results containing file_path, score distance, and matched document.
        """
        # Execute query utilizing implicit local model embeddings
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        # Reformulate Chroma output vectors into cleanly mapped Dict abstractions
        processed_results: List[Dict[str, Any]] = []
        
        # Chroma returns complex list groupings [[doc1, doc2]] for batches. 
        # Safely index assuming singlular queries.
        if results and results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            
            for doc, meta, dist, node_id in zip(docs, metadatas, distances, results.get("ids", [[]])[0]): # type: ignore
                processed_results.append({
                    "node_id": node_id,
                    "file_path": meta.get("file_path", "unknown") if meta else "unknown",
                    "distance": dist,
                    "document": doc
                })
                
        return processed_results
