import hashlib
import time
import uuid
import asyncio

from pymilvus import (
    AnnSearchRequest,
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    Function,
    FunctionType,
    WeightedRanker,
    connections,
    db,
    utility,
)
from functools import partial
from typing import Any

CONTENT_SPARSE_FIELD = "content_sparse"
CONTENT_ANALYZER_PARAMS = {"type": "chinese"}

def hashstr(input_string, length=None, with_salt=False, salt=None):
    """生成字符串的哈希值
    Args:
        input_string: 输入字符串
        length: 截取长度，默认为None，表示不截取
        with_salt: 是否加盐，默认为False
    """
    try:
        # 尝试直接编码
        encoded_string = str(input_string).encode("utf-8")
    except UnicodeEncodeError:
        # 如果编码失败，替换无效字符
        encoded_string = str(input_string).encode("utf-8", errors="replace")

    if with_salt:
        if not salt:
            # 使用时间戳+随机数的组合作为salt，确保唯一性
            salt = f"{time.time()}_{uuid.uuid4().hex[:8]}"
        encoded_string = (encoded_string.decode("utf-8") + salt).encode("utf-8")

    hash = hashlib.sha256(encoded_string).hexdigest()
    if length:
        return hash[:length]
    return hash

def _create_new_collection(self, collection_name: str, embed_info: Any, db_id: str) -> Collection:
       """创建新的 Milvus 集合"""
       embedding_dim = embed_info.get("dimension", 1024)
       model_name = embed_info.get("name", "default")

        # 定义集合Schema
       fields = [
           FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
           FieldSchema(
               name="content",
               dtype=DataType.VARCHAR,
               max_length=65535,
               enable_analyzer=True,
               analyzer_params=CONTENT_ANALYZER_PARAMS,
           ),
           FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=500),
           FieldSchema(name="docs", dtype=DataType.VARCHAR, max_length=100),
           FieldSchema(name="subject", dtype=DataType.INT64),
           FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
           FieldSchema(name=CONTENT_SPARSE_FIELD, dtype=DataType.SPARSE_FLOAT_VECTOR),
       ]
       bm25_function = Function(
           name="content_bm25",
           input_field_names=["content"],
           output_field_names=[CONTENT_SPARSE_FIELD],
           function_type=FunctionType.BM25,
       )

       schema = CollectionSchema(
           fields=fields,
           description=f"Knowledge base collection for {db_id} using {model_name}",
           functions=[bm25_function],
       )

       # 创建集合
       collection = Collection(name=collection_name, schema=schema, using=self.connection_alias)

       # 创建索引
       index_params = {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 1024}}
       collection.create_index("embedding", index_params)
       sparse_index_params = {
           "metric_type": "BM25",
           "index_type": "SPARSE_INVERTED_INDEX",
           "params": {"inverted_index_algo": "DAAT_MAXSCORE"},
       }
       collection.create_index(CONTENT_SPARSE_FIELD, sparse_index_params)

       return collection

async def main():
    work_dir: str = 'lpx_demo'
    connection_alias = f"milvus_{hashstr(work_dir, 6)}"
    connections.connect(alias=connection_alias, uri='http://192.168.31.75:19530', token="")
    connections.get_connection_addr(connection_alias)
    milvus_db: str = 'lpx_demo'
    if milvus_db not in db.list_database(using=connection_alias):
        db.create_database(milvus_db, using=connection_alias)
    db.using_database(milvus_db, using=connection_alias)
    from yuxi.models.embed import select_embedding_model

    embedding_model = select_embedding_model("siliconflow/Pro/BAAI/bge-m3")
    batch_size = int(getattr(embedding_model, "batch_size", 40) or 40)
    docs = ['hrthtryhtr']
    vectors_w = await embedding_model.abatch_encode(messages = docs,batch_size=batch_size)
    vectors = [vectors_w]
    data = [
        {"id": i, "vector": vectors[i], "text": docs[i], "subject": "history"}
        for i in range(len(vectors))
    ]
    db.connections.insert(data)
    print(data)

if __name__ == "__main__":
    asyncio.run(main())
