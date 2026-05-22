import hashlib
import time
import uuid
import asyncio

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    Function,
    FunctionType,
    connections,
    db,
    utility,
)

CONTENT_SPARSE_FIELD = "content_sparse"
CONTENT_ANALYZER_PARAMS = {"type": "chinese"}

def hashstr(input_string, length=None, with_salt=False, salt=None):
    """生成字符串的哈希值"""
    try:
        encoded_string = str(input_string).encode("utf-8")
    except UnicodeEncodeError:
        encoded_string = str(input_string).encode("utf-8", errors="replace")

    if with_salt:
        if not salt:
            salt = f"{time.time()}_{uuid.uuid4().hex[:8]}"
        encoded_string = (encoded_string.decode("utf-8") + salt).encode("utf-8")

    hash_val = hashlib.sha256(encoded_string).hexdigest()
    if length:
        return hash_val[:length]
    return hash_val


def create_collection(connection_alias: str, collection_name: str, embedding_dim: int, model_name: str) -> Collection:
    """创建 Milvus Collection"""
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
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=100),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
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
        description=f"Knowledge base collection for {collection_name} using {model_name}",
        functions=[bm25_function],
    )

    collection = Collection(name=collection_name, schema=schema, using=connection_alias)

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

    # 1. 连接 Milvus
    connections.connect(alias=connection_alias, uri='http://192.168.31.75:19530', token="")
    print(f"Connected to Milvus: {connections.get_connection_addr(connection_alias)}")

    # 2. 创建/切换数据库
    milvus_db: str = 'lpx_demo'
    if milvus_db not in db.list_database(using=connection_alias):
        db.create_database(milvus_db, using=connection_alias)
        print(f"Created database: {milvus_db}")
    db.using_database(milvus_db, using=connection_alias)

    # 3. 获取 embedding 模型
    from yuxi.models.embed import select_embedding_model
    embedding_model = select_embedding_model("siliconflow/Pro/BAAI/bge-m3")
    batch_size = int(getattr(embedding_model, "batch_size", 40) or 40)

    # 4. 生成向量
    docs = ["今天天气不错", "Python是一门编程语言", "Milvus是向量数据库"]
    embeddings = await embedding_model.abatch_encode(docs, batch_size=batch_size)
    print(f"Generated embeddings: {len(embeddings)} vectors, dim={len(embeddings[0])}")

    # 5. 创建或获取 Collection
    collection_name = "demo_collection"
    embedding_dim = len(embeddings[0])

    if utility.has_collection(collection_name, using=connection_alias):
        utility.drop_collection(collection_name, using=connection_alias)
        print(f"Dropped existing collection: {collection_name}")

    collection = create_collection(connection_alias, collection_name, embedding_dim, "bge-m3")
    print(f"Created collection: {collection_name}")

    # 6. 插入数据 — Milvus 要求按字段顺序传入 list[list]
    import uuid as _uuid
    ids = [str(_uuid.uuid4()) for _ in docs]
    chunk_ids = [str(_uuid.uuid4()) for _ in docs]
    file_ids = ["file_001"] * len(docs)
    chunk_indices = list(range(len(docs)))
    sources = ["source1", "source2", "source3"]

    data = [
        ids,            # id (VARCHAR, primary key)
        docs,           # content (VARCHAR)
        sources,        # source (VARCHAR)
        chunk_ids,      # chunk_id (VARCHAR)
        file_ids,       # file_id (VARCHAR)
        chunk_indices,  # chunk_index (INT64)
        embeddings,     # embedding (FLOAT_VECTOR)
        # content_sparse 由 BM25 Function 自动填充，不需要手动传入
    ]

    collection.insert(data)
    print(f"Inserted {len(docs)} records")

    # 7. 测试搜索
    collection.load()
    query_text = "编程语言"
    query_embedding = await embedding_model.abatch_encode([query_text], batch_size=batch_size)

    results = collection.search(
        data=query_embedding,
        anns_field="embedding",
        param={"metric_type": "COSINE", "params": {"nprobe": 10}},
        limit=3,
        output_fields=["content", "source"],
    )

    print(f"\n搜索 '{query_text}' 结果:")
    for hits in results:
        for hit in hits:
            print(f"  score={hit.distance:.4f}  content={hit.entity.get('content')}")


if __name__ == "__main__":
    asyncio.run(main())
