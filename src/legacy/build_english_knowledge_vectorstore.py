#!/usr/bin/env python3
"""
Build Comprehensive English Knowledge Vector Store
Processes all knowledge base files and creates unified embeddings for RAG system
"""

import os
import sys
from pathlib import Path
from typing import List

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document


def read_knowledge_files() -> List[Document]:
    """Read all knowledge base files from knowledge/ directory"""

    print("\n" + "="*70)
    print("📚 Reading English Knowledge Base Files")
    print("="*70 + "\n")

    knowledge_dir = project_root / "knowledge"
    if not knowledge_dir.exists():
        print(f"❌ Knowledge directory not found: {knowledge_dir}")
        return []

    documents = []
    markdown_files = list(knowledge_dir.glob("*.md")) + list(knowledge_dir.glob("*.txt"))

    if not markdown_files:
        print(f"❌ No knowledge files found in {knowledge_dir}")
        return []

    print(f"📖 Found {len(markdown_files)} files to process:\n")

    for file_path in sorted(markdown_files):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Create document with metadata
            doc = Document(
                page_content=content,
                metadata={
                    "source": file_path.name,
                    "path": str(file_path),
                    "type": "knowledge_base"
                }
            )
            documents.append(doc)
            print(f"   ✅ {file_path.name:30} ({len(content):6} chars)")

        except Exception as e:
            print(f"   ⚠️  {file_path.name:30} (Error: {e})")

    print(f"\n📊 Total content read: {sum(len(d.page_content) for d in documents)} characters")
    return documents


def split_documents(documents: List[Document]) -> List[Document]:
    """Split documents into semantic chunks"""

    print("\n" + "="*70)
    print("✂️  Splitting Documents into Chunks")
    print("="*70 + "\n")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,          # Larger chunks for semantic meaning
        chunk_overlap=200,         # Overlap for context
        separators=[
            "\n## ",              # Markdown H2
            "\n### ",             # Markdown H3
            "\n#### ",            # Markdown H4
            "\n\n",               # Paragraph break
            "\n",                 # Line break
            ". ",                 # Sentence
            " ",                  # Word
            ""                    # Character
        ]
    )

    chunks = []
    for doc in documents:
        split_docs = splitter.split_documents([doc])
        chunks.extend(split_docs)
        print(f"   {doc.metadata['source']:30} → {len(split_docs):3} chunks")

    print(f"\n📊 Total chunks created: {len(chunks)}")
    return chunks


def build_vectorstore(chunks: List[Document]) -> bool:
    """Build and persist Chroma vector store"""

    print("\n" + "="*70)
    print("🔧 Building Vector Store with OpenAI Embeddings")
    print("="*70 + "\n")

    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not set")
        print("Please set: export OPENAI_API_KEY=sk-...")
        return False

    # Initialize embeddings
    print("📡 Initializing OpenAI Embeddings (text-embedding-3-small)...")
    try:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=api_key
        )
        print("   ✅ Embeddings model ready")
    except Exception as e:
        print(f"   ❌ Failed to initialize embeddings: {e}")
        return False

    # Create vector store
    vectorstore_path = project_root / "knowledge_db"
    print(f"\n🗄️  Creating Chroma vector store at: {vectorstore_path}")
    print(f"   Processing {len(chunks)} chunks...")

    try:
        # Remove existing database if present
        import shutil
        if vectorstore_path.exists():
            print(f"   🔄 Removing existing database...")
            shutil.rmtree(vectorstore_path)

        # Create new vector store
        vectorstore = Chroma.from_documents(
            chunks,
            embeddings,
            persist_directory=str(vectorstore_path)
        )

        print(f"\n   ✅ Vector store created successfully")

        # Verify
        try:
            collection = vectorstore.get()
            print(f"\n📊 Vector Store Statistics:")
            print(f"   • Total embeddings: {len(collection['ids'])}")
            print(f"   • Documents indexed: {len(set(doc.metadata.get('source', 'unknown') for doc in chunks))}")
            print(f"   • Database size: ~{(vectorstore_path.stat().st_size / 1024 / 1024):.2f} MB")
        except Exception as e:
            print(f"   ⚠️  Could not verify collection: {e}")

        return True

    except Exception as e:
        print(f"\n   ❌ Failed to create vector store: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_retrieval(vectorstore_path: str = None):
    """Test vector store retrieval with sample queries"""

    print("\n" + "="*70)
    print("🧪 Testing Retrieval")
    print("="*70 + "\n")

    if not vectorstore_path:
        vectorstore_path = project_root / "knowledge_db"

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  Skipping retrieval test (OPENAI_API_KEY not set)")
        return

    try:
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=api_key
        )
        vectorstore = Chroma(
            persist_directory=str(vectorstore_path),
            embedding_function=embeddings
        )
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

        # Test queries
        test_queries = [
            "How much does VC farming cost?",
            "What is the reputation tier boosting price?",
            "level up service pricing",
            "platform multipliers for different consoles",
            "order process and timeline"
        ]

        print(f"Running {len(test_queries)} test queries:\n")

        for i, query in enumerate(test_queries, 1):
            print(f"{i}. Query: \"{query}\"")
            try:
                results = retriever.invoke(query)
                print(f"   Found {len(results)} results")
                if results:
                    # Show first result summary
                    first_result = results[0].page_content[:150].replace('\n', ' ')
                    print(f"   Preview: {first_result}...")
                print()
            except Exception as e:
                print(f"   Error: {e}\n")

        print("✅ Retrieval test complete")

    except Exception as e:
        print(f"❌ Retrieval test failed: {e}")


def main():
    """Main build process"""
    try:
        print("\n" + "="*70)
        print("🚀 Building Comprehensive English Knowledge Vector Store")
        print("="*70)

        # Step 1: Read files
        documents = read_knowledge_files()
        if not documents:
            print("\n❌ No documents to process")
            return False

        # Step 2: Split documents
        chunks = split_documents(documents)
        if not chunks:
            print("\n❌ Failed to split documents")
            return False

        # Step 3: Build vector store
        success = build_vectorstore(chunks)
        if not success:
            return False

        # Step 4: Test retrieval
        test_retrieval()

        print("\n" + "="*70)
        print("✅ Vector Store Build Complete!")
        print("="*70)
        print("\nNext steps:")
        print("  1. Update RAG Agent: RAGAgent(vectorstore_path='./knowledge_db')")
        print("  2. Run simple_bot.py with: python simple_bot.py")
        print("  3. Test with queries like: 'How much for 500K VC?'")
        print("\n")

        return True

    except KeyboardInterrupt:
        print("\n\n👋 Build interrupted by user")
        return False
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

