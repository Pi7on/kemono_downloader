import os
from sys import platform
import argparse
import requests as r
from datetime import datetime
from lxml import html

URL_WEB = "https://kemono.su/"
URL_API = URL_WEB + "api/v1/"
ATTACHMENT_DATA_PREFIX = "https://c5.kemono.su/data"

def get_creator_post_count(service, creator_id) -> int:
    url = f'{URL_WEB}{service}/user/{creator_id}'
    res = r.get(url)
    if res.status_code == 200:
        tree = html.fromstring(res.content)
        xpath_expr = "/html/body/div[2]/main/section/div[1]/small"
        
        # Use XPath to find matching elements
        matches = tree.xpath(xpath_expr)
        for m in matches:
            text:str = m.text_content()
            if text.find("Showing"):
                text = text.split("of")[1].strip()
                return int(text)
            else:
                print(f'ERROR: Could not get post count for creator: {creator_id} at service {service}')
                exit(1)
    else :
        print(f'ERROR: Could not get post count for creator: {creator_id} at service {service}')
        exit(1)
                
def get_posts(service, creator_id) -> list:
    posts = []
    post_count = get_creator_post_count(service, creator_id)
    if post_count is not None:
        for offset in range(0, post_count, 50):
            url = f'{URL_API}{service}/user/{creator_id}?o={offset}'
            res = r.get(url)
            if res.status_code == 200:
                print("GET: " + url)
                posts.extend(res.json())
            else:
                print(f'ERROR: Failed to retrieve page at offset {offset} - Status code: {res.status_code}')
    return sorted(posts, key=lambda x: x["published"], reverse=False)

if __name__ == "__main__":
    # Create ArgumentParser object
    parser = argparse.ArgumentParser(description="kemono.su dowloader")

    # Add arguments
    parser.add_argument('--file-format','-f', default="png", dest="formats", nargs='+', required=True, help="Space-separated list of file extensions to be dowloaded.")
    parser.add_argument('--out-path','-o', default="./kemono_dump", dest="outpath" ,type=str, help="Path where aria2 will download the files.")
    parser.add_argument('--creator-id','-cid', default="", dest="creator_id" ,type=int, required=True, help="https://kemono.su/patreon/user/12345678 <-- this number")
    parser.add_argument('--service','-srv', default="", dest="service" ,type=str, required=True, help="The service the content comes from. E.g. patreon, gumroad, etc.")

    # Parse arguments
    args = parser.parse_args()
    
    # Convert to Unix path for aria2
    if platform == "win32": #dumb
        args.outpath = args.outpath.replace("\\","/")
        
    posts = get_posts(args.service, args.creator_id)
    for format in args.formats:
        with open(f'aria_{args.service}_{args.creator_id}_{format}.txt', 'w') as file:
            for post in posts:
                publish = datetime.fromisoformat(post["published"])
                for att in post["attachments"]:
                    if str(att["path"]).endswith("." + format):
                        att_url = ATTACHMENT_DATA_PREFIX + att["path"]
                        att_filename = publish.strftime("%Y_%m_%d_%H_%M_%S") + "-" + att_url.split("data/")[1].replace("/", "_")
                    
                        
                        out_dir = args.outpath + "/" + format.upper() # aria2 expects unix-link file paths
                        if not os.path.exists(out_dir + "/" + att_filename):
                            aria_entry = f'{att_url}\n\tdir={out_dir}\n\tout={att_filename}\n'
                            file.write(aria_entry)
                        else:
                            print(args.outpath + att_filename + " already downloaded")
    



    
