"""
向量数据库模块

使用 ChromaDB 存储风格案例的向量嵌入，支持语义相似度检索。
主要功能：
- 将风格案例文本向量化并存入 ChromaDB
- 根据查询文本检索最相似的案例
"""

import os
from typing import List, Dict, Optional, Any

import chromadb
from chromadb.config import Settings
import yaml
from loguru import logger


def _load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class VectorStore:
    """
    ChromaDB 向量存储封装类

    使用 ChromaDB 内置的 embedding 模型（all-MiniLM-L6-v2）
    对内容进行向量化，支持按风格分组检索。
    """

    def __init__(self):
        config = _load_config()
        vdb_cfg = config["vector_db"]

        persist_dir = vdb_cfg.get("persist_directory", "./chroma_data")
        os.makedirs(persist_dir, exist_ok=True)

        # 初始化 ChromaDB 持久化客户端
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        collection_name = vdb_cfg.get("collection_name", "style_examples")

        # 获取或创建集合（使用 ChromaDB 内置的 embedding 函数）
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},  # 使用余弦相似度
        )

        logger.info(f"ChromaDB 初始化完成，集合: {collection_name}，当前文档数: {self.collection.count()}")

    def add_example(
        self,
        doc_id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> None:
        """
        添加单条案例到向量库

        Args:
            doc_id  : 文档唯一 ID（建议使用数据库主键）
            text    : 需要向量化的文本（标题 + 正文）
            metadata: 附加元数据（style_name, title, tags 等）
        """
        self.collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata],
        )
        logger.debug(f"向量库添加文档: {doc_id}")

    def add_examples_batch(
        self,
        doc_ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """批量添加案例到向量库"""
        if not doc_ids:
            return
        self.collection.upsert(
            ids=doc_ids,
            documents=texts,
            metadatas=metadatas,
        )
        logger.info(f"批量向量化添加 {len(doc_ids)} 条案例")

    def search_similar(
        self,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        根据查询文本检索最相似的案例

        Args:
            query_text: 查询文本（如风格描述或主题）
            n_results : 返回结果数量
            where     : 元数据过滤条件（如 {"style_name": "原木风"}）

        Returns:
            相似案例列表，每条包含 id、text、metadata、distance
        """
        kwargs: Dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(n_results, max(self.collection.count(), 1)),
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        # 整理返回结果
        output = []
        if results and results.get("ids"):
            ids = results["ids"][0]
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0]
            for i, doc_id in enumerate(ids):
                output.append({
                    "id": doc_id,
                    "text": docs[i],
                    "metadata": metas[i],
                    "distance": distances[i],
                    "similarity": 1 - distances[i],  # 转换为相似度
                })

        logger.debug(f"向量检索 '{query_text}' 返回 {len(output)} 条结果")
        return output

    def search_by_style(self, style_name: str, query_text: str, n_results: int = 5) -> List[Dict]:
        """按风格过滤的语义检索"""
        return self.search_similar(
            query_text=query_text,
            n_results=n_results,
            where={"style_name": style_name},
        )

    def delete_example(self, doc_id: str) -> None:
        """删除指定文档"""
        self.collection.delete(ids=[doc_id])
        logger.debug(f"向量库删除文档: {doc_id}")

    def get_total_count(self) -> int:
        """获取向量库中的文档总数"""
        return self.collection.count()
