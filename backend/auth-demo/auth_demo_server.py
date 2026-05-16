"""
登录认证流程 Demo - 独立可运行，不依赖项目其他代码
启动: python auth_demo_server.py
访问: http://localhost:9000
"""

import asyncio
import hashlib
import hmac
import sys
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
import jwt
from sqlalchemy import Column, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ─── Windows 事件循环策略 ───
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ─── JWT 配置 ───
SECRET_KEY = "demo_secret_key_12345"
ALGORITHM = "HS256"
EXPIRE_MINUTES = 60

# ─── 密码哈希器 ───
ph = PasswordHasher()

# ─── 数据库（SQLite，零依赖） ───
DATABASE_URL = "sqlite+aiosqlite:///./auth_demo.db"
engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
class Base(DeclarativeBase):
    pass


# ─── User 模型 ───
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), unique=True, nullable=False)
    username = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
        }


# ─── Pydantic 响应模型 ───
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    role: str


class UserInfo(BaseModel):
    id: int
    user_id: str
    username: str
    role: str


# ─── 工具函数 ───
def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(stored: str, provided: str) -> bool:
    if stored.startswith("$argon2"):
        return ph.verify(stored, provided)
    # 兼容旧 SHA-256 格式
    if ":" not in stored:
        return False
    hashed, salt = stored.split(":", 1)
    check = hashlib.sha256((provided + salt).encode()).hexdigest()
    return hmac.compare_digest(hashed, check)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


# ─── 依赖注入 ───
async def get_db():
    async with SessionLocal() as session:
        yield session


async def get_user_from_token(token: str, db: AsyncSession) -> User | None:
    """从 JWT 解析用户"""
    payload = decode_token(token)
    if not payload:
        return None
    uid = payload.get("sub")
    if not uid:
        return None
    result = await db.execute(select(User).where(User.id == int(uid)))
    return result.scalar_one_or_none()


async def require_token(authorization: str | None = Header(None),user_agent: str | None = Header(None)):
    print(user_agent)
    """提取 Bearer Token，失败抛出 401"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return authorization.split("Bearer ", 1)[1]


# ─── FastAPI 应用 ───
app = FastAPI(title="登录认证 Demo")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


@app.get("/")
async def index():
    return FileResponse("auth-demo/index.html")


@app.post("/api/auth/token", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    登录接口：用 user_id + 密码换取 JWT
    防止用户名枚举：账号不存在和密码错误返回相同提示
    """
    # 查找用户（支持 user_id 和 username 登录）
    result = await db.execute(select(User).where(User.user_id == form.username))
    user = result.scalar_one_or_none()
    if not user:
        result = await db.execute(select(User).where(User.username == form.username))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="账号或密码错误")

    if not verify_password(user.password_hash, form.password):
        raise HTTPException(status_code=401, detail="账号或密码错误")

    # 生成 Token
    token = create_access_token(str(user.id))

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
    }


@app.get("/api/auth/me", response_model=UserInfo)
async def get_me(token: str = Depends(require_token), db: AsyncSession = Depends(get_db)):
    """获取当前登录用户信息 — 需要携带 Bearer Token"""
    user = await get_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="无效或过期的 Token")
    return user.to_dict()


@app.get("/api/protected")
async def protected_resource(token: str = Depends(require_token), db: AsyncSession = Depends(get_db)):
    """受保护的 API — 只有登录用户才能访问"""
    user = await get_user_from_token(token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效")
    return {
        "message": f"你好 {user.username}！这是受保护的资源",
        "your_role": user.role,
        "token_info": decode_token(token),
    }


@app.post("/api/auth/init")
async def init_demo(db: AsyncSession = Depends(get_db)):
    """初始化演示用户（首次启动自动创建）"""
    # 检查是否已有数据
    result = await db.execute(select(User))
    if result.scalars().all():
        return {"message": "演示用户已存在"}

    users = [
        User(user_id="admin", username="管理员", password_hash=hash_password("admin123"), role="admin"),
        User(user_id="user01", username="普通用户", password_hash=hash_password("user123"), role="user"),
    ]
    for u in users:
        db.add(u)
    await db.commit()
    return {"message": "已创建演示用户: admin/admin123, user01/user123"}


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        result = await s.execute(select(User))
        if not result.scalars().all():
            users = [
                User(user_id="admin", username="管理员", password_hash=hash_password("admin123"), role="admin"),
                User(user_id="user01", username="普通用户", password_hash=hash_password("user123"), role="user"),
            ]
            for u in users:
                s.add(u)
            await s.commit()
            print("  Demo users created:")
            print("    admin / admin123")
            print("    user01 / user123")


if __name__ == "__main__":
    import os
    import uvicorn

    cert_path = os.path.join(os.path.dirname(__file__), "cert.pem")
    key_path = os.path.join(os.path.dirname(__file__), "key.pem")

    if os.path.exists(cert_path) and os.path.exists(key_path):
        print("  Found SSL certificates, starting HTTPS server on https://localhost:9000")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=9000,
            ssl_certfile=cert_path,
            ssl_keyfile=key_path,
        )
    else:
        print("  No SSL certificate found, starting HTTP server on http://localhost:9000")
        print("  To enable HTTPS, run:")
        print("    openssl req -x509 -newkey rsa:2048 -keyout auth-demo/key.pem -out auth-demo/cert.pem -days 365 -nodes -subj '//CN=localhost'")
        uvicorn.run(app, host="0.0.0.0", port=9000)
