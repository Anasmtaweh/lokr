import chromadb
from pathlib import Path
from typing import Dict, Any, List

class CodebaseVectorDB:
    """
    Semantic search engine utilizing ChromaDB.
    Indexes parsed generic AST elements (Classes, Functions, Docstrings) 
    into a persistent local vector store for neural retrieval.
    """

    def __init__(self, db_dir: str | Path = "data/vector_store") -> None:
        """
        Initializes the ChromaDB persistent client pointing to the local directory,
        and ensures the required AST collection exists.

        Args:
            db_dir (str | Path): Relative or absolute path to the local vector storage root.
        """
        self.db_path = Path(db_dir).resolve()
        
        # Initialize Persistent Client (which automatically handles local sqlite+parquet embedding)
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        
        # Get or create the core collection
        self.collection = self.client.get_or_create_collection(name="codebase_ast")

    def index_file(self, parsed_data: Dict[str, Any]) -> None:
        """
        Formulates a semantic text document from a parsed AST JSON dictionary,
        and upserts it into the local Chroma collection seamlessly.

        Args:
            parsed_data (Dict[str, Any]): The structured output direct from CodeParser.
        """
        file_path_str: str = parsed_data.get("file_path", "unknown")
        
        # Formulate Document String
        doc_lines: List[str] = [f"File: {file_path_str}"]
        
        classes: List[Dict[str, Any]] = parsed_data.get("classes", [])
        if classes:
            class_names: List[str] = [c.get("name", "") for c in classes]
            doc_lines.append(f"Classes: {', '.join(class_names)}")
            
        functions: List[Dict[str, Any]] = parsed_data.get("functions", [])
        if functions:
            doc_lines.append("Functions:")
            for func in functions:
                func_name: str = func.get("name", "unknown")
                func_params: List[str] = func.get("parameters", [])
                params_str: str = ", ".join(func_params)
                docstring: str = func.get("docstring") or "No docstring provided."
                
                doc_lines.append(f"  - def {func_name}({params_str}):")
                doc_lines.append(f"      \"\"\"{docstring}\"\"\"")

        # Compile rich text body
        document_text: str = "\n".join(doc_lines)

        # Upsert into Chroma (Chroma implicitly embeds this text using its local all-MiniLM-L6-v2 model)
        # We map document ID purely against absolute file_path guaranteeing no collisions naturally.
        self.collection.upsert(
            documents=[document_text],
            metadatas=[{"file_path": file_path_str}],
            ids=[file_path_str]
        )

    def delete_file(self, filepath: Path) -> None:
        """
        Removes a document from the ChromaDB collection by its file path ID.
        Called when a file is deleted from the repository during incremental sync.

        Args:
            filepath (Path): The absolute path of the file to remove from the index.
        """
        doc_id = str(filepath.resolve())
        try:
            self.collection.delete(ids=[doc_id])
        except Exception as e:
            print(f"[WATCHMAN] Warning: Could not delete {doc_id} from index: {e}")

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
            
            for doc, meta, dist in zip(docs, metadatas, distances): # type: ignore
                processed_results.append({
                    "file_path": meta.get("file_path", "unknown") if meta else "unknown",
                    "distance": dist,
                    "document": doc
                })
                
        return processed_results
