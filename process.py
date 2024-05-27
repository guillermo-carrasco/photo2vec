"""
Functions to process a Google Photos export.

They should be run in the export director.
"""

import json
import os
import shutil

import pandas as pd
import pillow_heif
from PIL import Image, UnidentifiedImageError
from dateutil import parser


def extract_metadata(photo):
    return {
        "id": photo["url"].split("/")[-1],
        "title": photo["title"],
        "file_type": photo["title"].split(".")[-1].upper(),
        "url": photo["url"],
        "description": photo["description"],
        "creation_time": parser.parse(photo["creationTime"]["formatted"]),
        "photo_taken_time": parser.parse(photo["photoTakenTime"]["formatted"]),
        "latitude": (photo["geoData"]["latitude"] if photo["geoData"]["latitude"] != 0 else None),
        "longitude": (photo["geoData"]["longitude"] if photo["geoData"]["longitude"] != 0 else None),
        "altitude": photo["geoData"]["altitude"],
        "people": ({person["name"] for person in photo["people"]} if "people" in photo else None),
    }


def resize_image(image_path, resize_width=256):
    try:
        img = Image.open(image_path)
    # Some HEIC images edited in Google Photos can be directly loaded
    # with PIL.Image, this is why I don't look for .heic extension
    # but rather just try to use pillow_heif when regular load fails
    except UnidentifiedImageError:
        with open(image_path, "rb") as fp:
            heif_file = pillow_heif.open_heif(fp)
            img = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )

    # Resize the image while maintaining the aspect ratio
    width_percent = resize_width / float(img.size[0])
    new_height = int((float(img.size[1]) * float(width_percent)))
    img = img.resize((resize_width, new_height), Image.LANCZOS)

    return img


def process_export(export_dir):
    """Preprocess a Google Photos export directory (named "Takeout X")

    1. Resize every picture ("JPG", "HEIC", "JPEG", "PNG") to 256px width.
    2. Parse all metadata files and build a CSV with information for all the pictures in the library
    """
    out_dir = os.path.join(export_dir, "preprocessed")
    images_dir = os.path.join(out_dir, "images")
    metadata_dir = os.path.join(out_dir, "metadata")
    os.mkdir(out_dir)
    os.mkdir(images_dir)
    os.mkdir(metadata_dir)
    keep_formats = ["JPG", "HEIC", "JPEG", "PNG"]
    print(f"Processing {export_dir}...")
    n_files = n_images = n_metadata = n_failed = 0
    for dirpath, dirnames, filenames in os.walk(export_dir):
        for filename in filenames:
            n_files += 1
            file_path = os.path.join(dirpath, filename)
            file_extension = filename.split(".")[-1]
            if file_extension.upper() in keep_formats:
                n_images += 1
                resized = resize_image(file_path)

                # Convert to RGB to ensure JPEG compatibility
                resized = resized.convert("RGB")
                resized.save(
                    os.path.join(images_dir, os.path.splitext(filename)[0] + ".jpeg"),
                    "JPEG",
                )

            # If it is a json metadata file, we want to extract picture metadata
            elif filename.endswith(".json"):
                n_metadata += 1
                shutil.copy(file_path, os.path.join(metadata_dir, filename))

            # Output some progress
            if n_files % 100 == 0:
                print(
                    f"Processed {n_files} files: {n_images} images, {n_metadata} metadata files, {n_failed} failed images..."
                )


def process_metadata(metadata_dir, save_csv=True):
    metadata = []
    for dirpath, _, filenames in os.walk(metadata_dir):
        for filename in filenames:
            if filename.endswith(".json"):
                # Some metadata files are not picture metadata
                with open(os.path.join(dirpath, filename), "r") as f:
                    try:
                        metadata.append(extract_metadata(json.load(f)))
                    except KeyError:
                        pass
    df = pd.DataFrame.from_records(metadata, index="id")

    if save_csv:
        df.to_csv("photos_metadata.cssv")

    return df
