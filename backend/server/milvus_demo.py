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
    embeddings_fx = partial(embedding_model.abatch_encode, batch_size=batch_size)
    embeddings = await embeddings_fx('牛逼')
    print(embeddings)

if __name__ == "__main__":
    asyncio.run(main())
