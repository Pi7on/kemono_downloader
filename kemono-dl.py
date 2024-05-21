from posixpath import join
from sys import platform
import argparse
import requests as r
from datetime import datetime
from lxml import html
import time
import unicodedata
import re
import json
import logging

# TODO: Searching by tag works: https://kemono.su/api/v1/posts?o=700&tag=high+resolution
# TODO: We grab some files as .bin, when their extension is actually specified in the file["name"] or attachment["name"]. This causes us to skip, for example, valid psd files because thir url looks like this: ".....bf893f.bin?f=PSD.psd"


URL_WEB = "https://kemono.su/"
URL_API = URL_WEB + "api/v1/"
ATTACHMENT_DATA_PREFIX = "https://c5.kemono.su/data"
REQUEST_DELAY_SECS = 1  # When a creator has lots of pages, requesting them too fast gets us rate limited. Let's be kind to the Kemono bros
POSTS_PER_PAGE = 50
PAGES_TO_DL_DEFAULT = 1 * POSTS_PER_PAGE

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

log = logging.getLogger(__name__)


def slugify(value, allow_unicode: bool, blank_substitute: str):
    # https://stackoverflow.com/questions/295135/turn-a-string-into-a-valid-filename
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    value = re.sub(r"[-\s]+", "-", value).strip("-_")
    return blank_substitute if not value else value


def get_creator_name(service, creator_id) -> str:
    url = f"{URL_WEB}{service}/user/{creator_id}"
    xpath_expr = "/html/body/div[2]/main/section/header/div[2]/h1/a/span[2]"
    res = r.get(url)
    if res.status_code != 200:
        log.warning(
            f"Could not get creator name for id: {creator_id} at service {service}"
        )
        log.warning(f"WARN: Using id: {creator_id} as default value")
        return str(creator_id)

    tree = html.fromstring(res.content)
    matches = tree.xpath(xpath_expr)  # Use XPath to find matching elements
    if matches:
        return slugify(matches[0].text_content(), True, str(creator_id))

    log.warning(f"Could not get creator name for id: {creator_id} at service {service}")
    log.warning(f"Using id: {creator_id} as default value")
    return str(creator_id)


def get_creator_post_count(service, creator_id) -> int:
    url = f"{URL_WEB}{service}/user/{creator_id}"
    xpath_expr = "/html/body/div[2]/main/section/div[1]/small"
    res = r.get(url)

    if res.status_code != 200:
        log.error(f"Received status code: {res.status_code}")
        log.error(
            f"Could not get post count for creator: {creator_id} at service {service}"
        )
        exit(1)

    tree = html.fromstring(res.content)
    matches = tree.xpath(xpath_expr)  # Use XPath to find matching elements
    for m in matches:
        text: str = m.text_content()
        if "Showing" in text:
            text = text.split("of")[1].strip()
            return int(text)

    # check if creator only has one page of posts (less than 50 posts total)
    card_list_container_xpath: str = "/html/body/div[2]/main/section/div[3]/div[2]"
    post_list_container = tree.xpath(card_list_container_xpath)
    if post_list_container:
        log.info(f"Creator {creator_id} only has one page of posts")
        return len(post_list_container[0].getchildren())

    log.error(
        f"Could not find post count in html page for creator: {creator_id} at service {service}"
    )
    exit(1)


def get_posts(url, from_offset, to_offset=PAGES_TO_DL_DEFAULT) -> list:
    posts = []
    service, creator_id, _ = parse_web_url(url)
    post_count = get_creator_post_count(service, creator_id)
    if post_count is not None:
        for offset in range(from_offset, to_offset, POSTS_PER_PAGE):
            url = f"{URL_API}{service}/user/{creator_id}?o={offset}"
            res = r.get(url)
            if res.status_code == 200:
                log.info("Getting:" + url)
                posts.extend(res.json())
            else:
                log.error(
                    f"Failed to retrieve page at offset {offset} - Status code: {res.status_code}"
                )
            if post_count > (5 * POSTS_PER_PAGE):
                time.sleep(REQUEST_DELAY_SECS)
    return sorted(posts, key=lambda x: x["published"], reverse=False)


def json_dump(data, filepath):
    with open(filepath, "w") as f:
        json.dump(data, f)


class Candidate:
    def __init__(self, publishdt: str, url: str):
        self.publishdt = publishdt
        self.url = url

    def __str__(self):
        return f"{self.publishdt} | {self.url}"


def print_candidates(candidates):
    for i, c in enumerate(candidates):
        print(f"[{i}] {c}")


def remove_duplicates_by_url(candidates):
    seen = set()
    uniques: list[Candidate] = []
    for c in candidates:
        if c.url not in seen:
            seen.add(c.url)
            uniques.append(c)
        else:
            log.info(f"Removing duplicate: {c.url}")
    return uniques


def parse_web_url(url):
    # Define the pattern to match the URL with or without the offset
    pattern = r"https://kemono.su/(\w+)/user/(\d+)(?:\?o=(\d+))?"
    match = re.match(pattern, url)

    if match:
        service = str(match.group(1))
        creator_id = int(match.group(2))
        page_offset = match.group(3)

        if page_offset is None:
            page_offset = 0

        if page_offset % 50 != 0:
            log.warning(f"Page offset: {page_offset} not a multiple of 50")
            page_offset = (page_offset // 50) * 50
            log.warning(f"Page offset coerced to: {page_offset}")

        return service, creator_id, int(page_offset)
    else:
        log.error(f"could not parse input url: {url}")
        return None, None, None


if __name__ == "__main__":
    # Create ArgumentParser object
    parser = argparse.ArgumentParser(description="kemono.su dowloader")

    # Add arguments

    parser.add_argument(
        "--input",
        "-i",
        default="",
        dest="input_url",
        type=str,
        required=True,
        help="TODO",
    )
    parser.add_argument(
        "--file-format",
        "-f",
        default="png",
        dest="formats",
        nargs="+",
        required=False,
        help="Space-separated list of file extensions to be dowloaded.",
    )
    parser.add_argument(
        "--list-formats",
        "-F",
        action=argparse.BooleanOptionalAction,
        default="",
        dest="available_formats",
        type=list[str],
        required=False,
        help="List all available file formats from the provided account. Does not download anything.",
    )
    parser.add_argument(
        "--out-path",
        "-o",
        default="./kemono_dump",
        dest="outpath",
        type=str,
        help="Path where aria2 will download the files.",
    )
    parser.add_argument(
        "--use-original-filename",
        "-of",
        action=argparse.BooleanOptionalAction,
        default="",
        dest="use_original_att_fname",
        type=bool,
        required=False,
        help="TODO",
    )

    # Parse arguments
    args = parser.parse_args()

    # Convert to Unix path for aria2
    if platform == "win32":  # dumb
        args.outpath = args.outpath.replace("\\", "/")

    service, creator_id, page_offset = parse_web_url(args.input_url)
    creator_name = get_creator_name(service, creator_id)
    creator_post_count = get_creator_post_count(service, creator_id)
    log.info(f"Service: {service}")
    log.info(f"Creator ID: {creator_id}")
    log.info(f"Creator Name: {creator_name}")
    log.info(f"Creator Post count: {creator_post_count}")

    creator_posts = get_posts(args.input_url, 0, creator_post_count)

    if args.available_formats:
        seen_formats = set()
        for post in creator_posts:
            if post["file"]:
                seen_formats.add(str(post["file"]["path"]).split(".")[1].lower())
            for att in post["attachments"]:
                seen_formats.add(str(att["path"]).split(".")[1].lower())
        log.info(f"Found formats: {seen_formats}")
        exit(0)

    candidates = []

    for format in args.formats:
        for post in creator_posts:
            if post["file"] and str(post["file"]["path"]).endswith("." + format):
                cand = Candidate(
                    datetime.fromisoformat(post["published"]), post["file"]["path"]
                )
                candidates.append(cand)
            for att in post["attachments"]:
                if str(att["path"]).endswith("." + format):
                    cand = Candidate(
                        datetime.fromisoformat(post["published"]), att["path"]
                    )
                    candidates.append(cand)

    candidates = remove_duplicates_by_url(candidates)

    aria_file_name: str = f"aria_{service}_{creator_name}_{format.upper()}.txt"
    aria_entries_count: int = 0
    with open(aria_file_name, "w") as aria_file:
        for c in candidates:
            if c.url.endswith(format):
                file_url = ATTACHMENT_DATA_PREFIX + c.url
                out_dir = join(
                    args.outpath,
                    # creator_name.lower() + "_" + str(creator_id),
                    creator_name.lower(),
                    format.upper(),
                )
                final_filename = (
                    c.publishdt.strftime("%Y_%m_%d_%H_%M_%S")
                    + "-"
                    + c.url.replace("/", "_").removeprefix("_")
                )
                aria_entry = f"{file_url}\n\tdir={out_dir}\n\tout={final_filename}\n"
                # print(aria_entry)
                aria_file.write(aria_entry)
                aria_entries_count += 1
    log.info(
        f"Succesfully wrote {aria_entries_count} entries to file: {aria_file_name}"
    )
