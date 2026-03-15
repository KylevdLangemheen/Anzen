from sqlalchemy import BigInteger, Column, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from anzen.data.database import Base


class Config(Base):
    """
    SQLAlchemy async ORM model for per-server configuration.

    Columns:
        server_id (BigInteger):     Primary key — Discord server (guild) snowflake ID.
        logchannel_id (BigInteger): ID of the channel used for log messages.
        modrole_id (BigInteger):    Optional ID of the moderator role.

    Examples:
        Create a config for a server::

            config = await Config.create(
                db,
                server_id=123456789,
                logchannel_id=987654321,
                modrole_id=111222333
            )

        Fetch a server's config (returns None if not found)::

            config = await Config.get(db, server_id=123456789)
            if config:
                print(config.logchannel_id)

        Update just the log channel::

            await Config.update(db, server_id=123456789, logchannel_id=999888777)

        Get all server configs::

            all_configs = await Config.get_all(db)
            for cfg in all_configs:
                print(cfg.server_id, cfg.logchannel_id)
    """

    __tablename__ = "config"
    server_id = Column(BigInteger, primary_key=True)
    logchannel_id = Column(BigInteger, nullable=False)
    modrole_id = Column(BigInteger, nullable=True)

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
