from collections.abc import Iterator
from itertools import chain


BACKGROUND_IMAGE_FIELDS = (
    "artworks.image_id, artworks.height, artworks.width, artworks.image_type.id, "
    "screenshots.image_id, screenshots.height, screenshots.width"
)

_ARTWORK_PRIORITIES = {2: 0, 3: 1}
_OTHER_ARTWORK_PRIORITY = 2
_SCREENSHOT_PRIORITY = 3


def _rank_images(
    images: list[dict], *, screenshot: bool = False
) -> Iterator[tuple[int, float, int, str]]:
    for image in images:
        image_id = image.get("image_id")
        width = image.get("width")
        height = image.get("height")
        if not isinstance(image_id, str) or not image_id.strip():
            continue
        if type(width) is not int or type(height) is not int or width < 1280 or height < 720:
            continue
        if not 1.5 <= width / height <= 2.4:
            continue

        image_type = image.get("image_type")
        image_type_id = image_type.get("id") if isinstance(image_type, dict) else image_type
        priority = (
            _SCREENSHOT_PRIORITY if screenshot
            else _ARTWORK_PRIORITIES.get(image_type_id, _OTHER_ARTWORK_PRIORITY)
        )
        yield priority, abs(width / height - 16 / 9), -(width * height), image_id.strip()


def compute_candidate_background(artworks: list[dict], screenshots: list[dict]) -> str | None:
    image = min(
        chain(_rank_images(artworks), _rank_images(screenshots, screenshot=True)),
        default=None,
    )
    return f"https://images.igdb.com/igdb/image/upload/t_720p/{image[-1]}.jpg" if image else None
