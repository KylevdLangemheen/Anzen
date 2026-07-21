from sqlalchemy import BigInteger, Boolean, Column, String, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from anzen.data.database import Base


class Config(Base):
    """
    SQLAlchemy async ORM model for per-server configuration.

    Columns:
        server_id (BigInteger):          Primary key — Discord server (guild) snowflake ID.
        logchannel_id (BigInteger):       ID of the channel used for log messages.
        modrole_ids (list[int]):          IDs of roles to ping on notifications. Empty list if none.
        moduser_ids (list[int]):          IDs of individual users to ping on notifications. Empty list if none.
        log_all_bans (bool):              Whether every ban should be logged, regardless of issuer.
        log_all_reasons (bool):           Whether the ban reason text should be logged.
        log_bans_override (str):          CLI flag override controlling ban logging behaviour.
        log_reasons_override (str):       CLI flag override controlling reason logging behaviour.
    """

    __tablename__ = "config"
    server_id = Column(BigInteger, primary_key=True)
    logchannel_id = Column(BigInteger, nullable=False)
    modrole_ids = Column(ARRAY(BigInteger), nullable=False, server_default="{}")
    moduser_ids = Column(ARRAY(BigInteger), nullable=False, server_default="{}")
    log_all_bans = Column(Boolean, nullable=False, server_default="true")
    log_all_reasons = Column(Boolean, nullable=False, server_default="true")
    log_bans_override = Column(String, nullable=False, server_default="--no-log")
    log_reasons_override = Column(String, nullable=False, server_default="--no-reason")

    @classmethod
    async def create(cls, db: AsyncSession, server_id: int, **kwargs):
        config = cls(server_id=server_id, **kwargs)
        db.add(config)
        await db.commit()
        await db.refresh(config)
        return config

    @classmethod
    async def get(cls, db: AsyncSession, server_id: int):
        try:
            config = await db.get(cls, server_id)
        except NoResultFound:
            return None
        return config

    @classmethod
    async def get_all(cls, db: AsyncSession):
        return (await db.execute(select(cls))).scalars().all()

    @classmethod
    async def update(cls, db: AsyncSession, server_id: int, **kwargs):
        config = await cls.get(db, server_id)
        if not config:
            return None
        for key, value in kwargs.items():
            setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
        return config

    @classmethod
    async def upsert(cls, db: AsyncSession, server_id: int, **kwargs):
        config = await cls.get(db, server_id)
        if config is None:
            return await cls.create(db, server_id=server_id, **kwargs)
        for key, value in kwargs.items():
            setattr(config, key, value)
        await db.commit()
        await db.refresh(config)
        return config
