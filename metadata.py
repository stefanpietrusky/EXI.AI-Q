"""
title: EXI.AI-Q V1 [EXIF + AI + Q]
author: stefanpietrusky
author_url: https://downchurch.studio/
version: 1.0
"""

import exiftool
from PIL import Image, PngImagePlugin
from pathlib import Path
import os

exiftool_path = Path(r"\exiftool.exe").resolve()

def set_metadata_jpg(image_path, metadata):
    import exiftool
    exiftool_path = Path(r"\exiftool.exe").resolve()
    with exiftool.ExifTool(str(exiftool_path)) as et:
        args = [f"-{k}={v}" for k, v in metadata.items()] + [image_path]
        et.execute(*args)
    print(f"Metadata for {image_path} (JPEG) updated!")

def set_metadata_png(image_path, metadata):
    img = Image.open(image_path)
    pnginfo = PngImagePlugin.PngInfo()
    if "Description" in metadata:
        pnginfo.add_itxt("Description", metadata["Description"], lang="", tkey="Description")
    for key, value in metadata.items():
        if key != "Description":
            pnginfo.add_text(key, value)
    img.save(image_path, "PNG", pnginfo=pnginfo)
    print(f"Metadata for {image_path} (PNG) updated!")

def set_metadata_gif(image_path, metadata):
    import exiftool
    exiftool_path = Path(r"\exiftool.exe").resolve()
    with exiftool.ExifTool(str(exiftool_path)) as et:
        args = [f"-XMP:{k}={v}" for k, v in metadata.items()] + [image_path]
        et.execute(*args)
    print(f"Metadata for {image_path} (GIF) updated!")

def set_metadata(image_path, metadata):
    ext = os.path.splitext(image_path)[1].lower()
    if ext in [".jpg", ".jpeg"]:
        set_metadata_jpg(image_path, metadata)
    elif ext == ".png":
        set_metadata_png(image_path, metadata)
    elif ext == ".gif":
        set_metadata_gif(image_path, metadata)
    else:
        print(f"Unsupported format: {ext}")

def read_metadata_from_txt(file_path):
    metadata_dict = {}
    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split("|")
            if len(parts) < 2:
                continue
            image_file = parts[0].strip()
            metadata = {}
            for entry in parts[1:]:
                if "=" not in entry:
                    continue
                key, value = entry.split("=", 1)  
                metadata[key.strip()] = value.strip()
            metadata_dict[image_file] = metadata
    return metadata_dict

def process_metadata_file(txt_file, image_directory):
    metadata_entries = read_metadata_from_txt(txt_file)

    for image_name, metadata in metadata_entries.items():
        image_path = os.path.join(image_directory, image_name)
        if os.path.isfile(image_path):
            set_metadata(image_path, metadata)
        else:
            print(f"File not found: {image_path}")

txt_file = r'\metadata.txt'
image_directory = r'\images' 

process_metadata_file(txt_file, image_directory)
