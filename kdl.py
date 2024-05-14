import os
from sys import platform
import argparse
import requests as r
from datetime import datetime
from lxml import html
from time import sleep
import unicodedata
import re
import json

URL_WEB = "https://kemono.su/"
URL_API = URL_WEB + "api/v1/"
ATTACHMENT_DATA_PREFIX = "https://c5.kemono.su/data"
REQUEST_DELAY_SECS = 1 # When a creator has lots of pages, requesting them too fast gets us rate limited. Let's be kind to the Kemono bros
POSTS_PER_PAGE = 50

def slugify(value, allow_unicode:bool, blank_substitute:str):
    """
    Taken from https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    value = re.sub(r'[-\s]+', '-', value).strip('-_')
    return blank_substitute if not value else value
    
def get_creator_name(service, creator_id) -> str:
    url = f'{URL_WEB}{service}/user/{creator_id}'
    xpath_expr = "/html/body/div[2]/main/section/header/div[2]/h1/a/span[2]"
    res = r.get(url)
    if res.status_code != 200:
        print(f'WARN: Could not get creator name for id: {creator_id} at service {service}')
        print(f'WARN: Using id: {creator_id} as default value')
        return str(creator_id)
    
    tree = html.fromstring(res.content)
    matches = tree.xpath(xpath_expr)  # Use XPath to find matching elements
    if matches:
        return slugify(matches[0].text_content(), True, str(creator_id))

    print(f'WARN: Could not get creator name for id: {creator_id} at service {service}')
    print(f'WARN: Using id: {creator_id} as default value')
    return str(creator_id)
        
def get_creator_post_count(service, creator_id) -> int:
    url = f'{URL_WEB}{service}/user/{creator_id}'
    xpath_expr = "/html/body/div[2]/main/section/div[1]/small"
    res = r.get(url)
    
    if res.status_code != 200:
        print(f'ERROR: Could not get post count for creator: {creator_id} at service {service}')
        exit(1)
    
    tree = html.fromstring(res.content)
    matches = tree.xpath(xpath_expr)  # Use XPath to find matching elements
    for m in matches:
        text:str = m.text_content()
        if "Showing" in text:
            text = text.split("of")[1].strip()
            return int(text)
    
    print(f'ERROR: Could not get post count for creator: {creator_id} at service {service}')
    exit(1)

                
def get_posts(service, creator_id) -> list:
    posts = []
    post_count = get_creator_post_count(service, creator_id)
    if post_count is not None:
        for offset in range(0, post_count, POSTS_PER_PAGE):
            url = f'{URL_API}{service}/user/{creator_id}?o={offset}'
            res = r.get(url)
            if res.status_code == 200:
                print("GET: " + url)
                posts.extend(res.json())
            else:
                print(f'ERROR: Failed to retrieve page at offset {offset} - Status code: {res.status_code}')
            if post_count > (5 * POSTS_PER_PAGE):
                sleep(REQUEST_DELAY_SECS)
    return sorted(posts, key=lambda x: x["published"], reverse=False)

def json_dump(data, filepath):
    with open(filepath, 'w') as f:
        json.dump(data, f)

if __name__ == "__main__":
    # Create ArgumentParser object
    parser = argparse.ArgumentParser(description="kemono.su dowloader")

    # Add arguments
    parser.add_argument('--file-format','-f', default="png", dest="formats", nargs='+', required=True, help="Space-separated list of file extensions to be dowloaded.")
    parser.add_argument('--out-path','-o', default="./kemono_dump", dest="outpath" ,type=str, help="Path where aria2 will download the files.")
    parser.add_argument('--creator-id','-cid', default="", dest="creator_id" ,type=int, required=True, help="https://kemono.su/patreon/user/12345678 <-- this number")
    parser.add_argument('--service','-srv', default="", dest="service" ,type=str, required=True, help="The service the content comes from. E.g. patreon, gumroad, etc.")
    parser.add_argument('--use-original-attachment-filename','-uoaf', action=argparse.BooleanOptionalAction, default="", dest="use_original_att_fname" ,type=bool, required=False, help="TODO")
    
    # Parse arguments
    args = parser.parse_args()
    
    # Convert to Unix path for aria2
    if platform == "win32": #dumb
        args.outpath = args.outpath.replace("\\","/")
    
    creator_name = get_creator_name(args.service, args.creator_id)
        
    posts = get_posts(args.service, args.creator_id)
    json_dump(posts, "./dump.json")
    # exit()
    
    for format in args.formats:
        with open(f'aria_{args.service}_{creator_name}_{format}.txt', 'w') as aria_file:
            for post in posts:
                publish = datetime.fromisoformat(post["published"])
                for att in post["attachments"]:
                    if str(att["path"]).endswith("." + format):
                        
                        att_name = att["name"]
                        att_path = ATTACHMENT_DATA_PREFIX + att["path"]
                        
                        if args.use_original_att_fname:
                            att_path += f'?f={att_name}' # Unnecessary? idk
                            final_filename = att_name
                        else:
                            final_filename = publish.strftime("%Y_%m_%d_%H_%M_%S") + "-" + att_path.split("data/")[1].replace("/", "_")
                    
                        out_dir = args.outpath + "/" + format.upper() # aria2 expects unix-link file paths
                        
                        aria_entry = f'{att_path}\n\tdir={out_dir}\n\tout={final_filename}\n'
                        aria_file.write(aria_entry)
                        
                # Some posts only have one file, and it's inside this object, not an attachment
                if post["file"]:
                    if str(post["file"]["path"]).endswith("." + format):
                        f_name = post["file"]["name"]
                        f_path = ATTACHMENT_DATA_PREFIX + post["file"]["path"]
                        
                        if args.use_original_att_fname:
                            att_path += f'?f={f_name}' # Unnecessary? idk
                            final_filename = f_name
                        else:
                            final_filename = publish.strftime("%Y_%m_%d_%H_%M_%S") + "-" + f_path.split("data/")[1].replace("/", "_")
                    
                        out_dir = args.outpath + "/" + format.upper() # aria2 expects unix-link file paths
                        
                        aria_entry = f'{f_path}\n\tdir={out_dir}\n\tout={final_filename}\n'
                        aria_file.write(aria_entry)
