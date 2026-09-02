"""Pagination utility for SQLAlchemy queries (P2-4)."""


def paginate_query(query, page=None, per_page=None, max_per_page=100):
    """Paginate a SQLAlchemy query.

    Returns a dict with items, total, page, per_page, pages.
    If page is None (no param provided), returns all items without pagination info.
    """
    if page is None and per_page is None:
        # Backward compatibility: return all items
        return query.all()

    page = max(1, int(page or 1))
    per_page = min(max(1, int(per_page or 20)), max_per_page)
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    pages = -(-total // per_page) if per_page else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }
