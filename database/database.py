"""
数据库连接管理模块

负责创建和管理 PostgreSQL 数据库连接，提供异步 Session 工厂。
使用 SQLAlchemy 2.x 异步引擎。
"""

import os
from typing import AsyncGenerator

import yaml
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from loguru import logger


def load_config() -> dict:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "../config/config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 加载配置
_config = load_config()
_db_cfg = _config["database"]

# 构造数据库连接 URL（使用 asyncpg 异步驱动）
DATABASE_URL = (
    f"postgresql+asyncpg://{_db_cfg['user']}:{_db_cfg['password']}"
    f"@{_db_cfg['host']}:{_db_cfg['port']}/{_db_cfg['name']}"
)

# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    pool_size=_db_cfg.get("pool_size", 10),
    max_overflow=_db_cfg.get("max_overflow", 20),
    echo=False,  # 生产环境关闭 SQL 日志
)

# 创建异步 Session 工厂
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入：提供数据库 Session。
    用法：
        @app.get("/")
        async def route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"数据库操作异常: {e}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """初始化数据库：创建所有表结构"""
    from database.models import StyleCategory, StyleTopic, StyleExample, PostRecord  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构初始化完成")


async def close_db() -> None:
    """关闭数据库连接池"""
    await engine.dispose()
    logger.info("数据库连接池已关闭")
