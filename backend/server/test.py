import asyncio

async def fetch_data(url: str) -> str:
    """异步函数，模拟网络请求"""
    await asyncio.sleep(5)  # 非阻塞等待
    return f"Data from {url}"


async def main():
    # 方式1：顺序执行
    print('----------1------------')
    result1 = asyncio.create_task(fetch_data("url1"))
    print('----------2------------')
    result2 = asyncio.create_task(fetch_data("url2"))
    print('----------3------------')
    await result1
    await result2
    print(result1.result())
    print(result2.result())

    print('----------4------------')
    # 方式2：并发执行（推荐）
    results = await asyncio.gather(
        fetch_data("url1"),
        fetch_data("url2")
    )
    print('----------5------------')
    print(results)
    print('----------6------------')

def count_up_to(n: int) -> int:
    """生成器函数，逐个产出值"""
    for i in range(1, n + 1):
        yield i  # 暂停并返回值，下次从这继续
        print('aaaaaaaaaaaaaaa')

def talk() -> int:
    yield 'hello'
    yield 'world'
    yield 'test'

async def async_stream_numbers(n: int):
    """异步生成器：每次产出前做一次异步操作"""
    for i in range(n):
        await asyncio.sleep(2)  # 模拟异步操作（如请求API）
        yield i
        await asyncio.sleep(2)
        print('aaaaaaaaaaaaaaa')

async def main2():
    async for num in async_stream_numbers(5):
        print(num)  # 每隔0.5秒输出一个


if __name__ == "__main__":
    # asyncio.run(main())  # 启动事件循环
    # 用法
    # for num in count_up_to(5):
    #     print(num)  # 1, 2, 3, 4, 5

    asyncio.run(main2())

    # tmp : list = list(talk())
    #
    # print(tmp)

