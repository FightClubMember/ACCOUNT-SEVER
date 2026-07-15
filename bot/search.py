from sqlalchemy import select, or_, and_, cast, String
from bot.database import async_session_maker
from bot.models import Account

async def search_accounts(query: str) -> list[Account]:
    """
    Search accounts in the database by Email, ID, Notes, Status, or Date.
    Supports partial matching and is case-insensitive.
    Excludes soft-deleted accounts.
    """
    query = query.strip()
    if not query:
        return []
        
    async with async_session_maker() as session:
        # Build search criteria
        conditions = [
            Account.email.ilike(f"%{query}%"),
            Account.notes.ilike(f"%{query}%"),
            Account.status.ilike(f"%{query}%")
        ]
        
        # Check if query is numeric (like ID)
        clean_query = query
        if query.startswith("#"):
            clean_query = query[1:]
            
        if clean_query.isdigit():
            conditions.append(Account.id == int(clean_query))
            
        # Partial match on created_at converted to string
        conditions.append(cast(Account.created_at, String).ilike(f"%{query}%"))
        
        # Query matching accounts, order by pinned first, then newest
        stmt = select(Account).where(
            and_(
                Account.deleted_at.is_(None),
                or_(*conditions)
            )
        ).order_by(Account.pinned.desc(), Account.created_at.desc())
        
        result = await session.execute(stmt)
        return list(result.scalars().all())
