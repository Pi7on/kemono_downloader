# kcdl

A kemono.su attachment downloader

## Features

- [x] Downlaod all the attachments from a given creator
- [x] Won't download/overwrite already downloaded files

## Usage

Clone the repo and install the dependencies:

```powershell
git clone <link>
cd here
pip install -r requirements.txt
```

Run the script:

```powershell
python .\kdl.py --platform <platform> --creatorid <id> --format <format> --outpath <path>
```

Executing the script will generate an input file for [aria2](https://aria2.github.io/) containing a list of files to downlaod, with an associated filename and output directory.

Each entry in the file looks like this, in compliance with aria2's specification:

```txt
https://c5.kemono.su/data/aa/bb/attachment.ext
    dir=/chosen/output/path
    out=filename.ext
```

Call aria2c with the generated downlaod list as input:

```powershell
aria2c -i file.txt -j 2 
```
