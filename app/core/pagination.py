from collections.abc import Sequence

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def paginate_sequence[T](items: Sequence[T], page: int, page_size: int) -> list[T]:
    start = (page - 1) * page_size
    return list(items[start : start + page_size])
