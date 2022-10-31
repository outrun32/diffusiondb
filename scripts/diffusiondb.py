# Copyright 2022  Jay Wang, Evan Montoya, David Munechika, Alex Yang, Ben Hoover, Polo Chau
# MIT License
"""Loading script for DiffusionDB."""

import numpy as np
import pandas as pd

from json import load, dump
from os.path import join, basename
from huggingface_hub import hf_hub_url

import datasets

# Find for instance the citation on arxiv or on the dataset repo/website
_CITATION = """\
@article{wangDiffusionDBLargescalePrompt2022,
  title = {{{DiffusionDB}}: {{A}} Large-Scale Prompt Gallery Dataset for Text-to-Image Generative Models},
  author = {Wang, Zijie J. and Montoya, Evan and Munechika, David and Yang, Haoyang and Hoover, Benjamin and Chau, Duen Horng},
  year = {2022},
  journal = {arXiv:2210.14896 [cs]},
  url = {https://arxiv.org/abs/2210.14896}
}
"""

# You can copy an official description
_DESCRIPTION = """
DiffusionDB is the first large-scale text-to-image prompt dataset. It contains 2
million images generated by Stable Diffusion using prompts and hyperparameters
specified by real users. The unprecedented scale and diversity of this
human-actuated dataset provide exciting research opportunities in understanding
the interplay between prompts and generative models, detecting deepfakes, and
designing human-AI interaction tools to help users more easily use these models.
"""

_HOMEPAGE = "https://poloclub.github.io/diffusiondb"
_LICENSE = "CC0 1.0"
_VERSION = datasets.Version("0.9.0")

# Programmatically generate the URLs for different parts
# hf_hub_url() provides a more flexible way to resolve the file URLs
# https://huggingface.co/datasets/poloclub/diffusiondb/resolve/main/images/part-000001.zip
_URLS = {}
_PART_IDS = range(1, 2001)

for i in _PART_IDS:
    _URLS[i] = hf_hub_url(
        "datasets/poloclub/diffusiondb", filename=f"images/part-{i:06}.zip"
    )

# Add the metadata parquet URL as well
_URLS["metadata"] = hf_hub_url(
    "datasets/poloclub/diffusiondb", filename=f"metadata.parquet"
)

_SAMPLER_DICT = {
    1: "ddim",
    2: "plms",
    3: "k_euler",
    4: "k_euler_ancestral",
    5: "ddik_heunm",
    6: "k_dpm_2",
    7: "k_dpm_2_ancestral",
    8: "k_lms",
    9: "others",
}


class DiffusionDBConfig(datasets.BuilderConfig):
    """BuilderConfig for DiffusionDB."""

    def __init__(self, part_ids, **kwargs):
        """BuilderConfig for DiffusionDB.
        Args:
          part_ids([int]): A list of part_ids.
          **kwargs: keyword arguments forwarded to super.
        """
        super(DiffusionDBConfig, self).__init__(version=_VERSION, **kwargs)
        self.part_ids = part_ids


class DiffusionDB(datasets.GeneratorBasedBuilder):
    """A large-scale text-to-image prompt gallery dataset based on Stable Diffusion."""

    BUILDER_CONFIGS = []

    # Programmatically generate configuration options (HF requires to use a string
    # as the config key)
    for num_k in [1, 5, 10, 50, 100, 500, 1000]:
        for sampling in ["first", "random"]:
            num_k_str = f"{num_k}k" if num_k < 1000 else f"{num_k // 1000}m"

            if sampling == "random":
                # Name the config
                cur_name = "random_" + num_k_str

                # Add a short description for each config
                cur_description = (
                    f"Random {num_k_str} images with their prompts and parameters"
                )

                # Sample part_ids
                part_ids = np.random.choice(_PART_IDS, num_k, replace=False).tolist()
            else:
                # Name the config
                cur_name = "first_" + num_k_str

                # Add a short description for each config
                cur_description = f"The first {num_k_str} images in this dataset with their prompts and parameters"

                # Sample part_ids
                part_ids = _PART_IDS[1 : num_k + 1]

            # Create configs
            BUILDER_CONFIGS.append(
                DiffusionDBConfig(
                    name=cur_name,
                    part_ids=part_ids,
                    description=cur_description,
                ),
            )

    # For the 2k option, random sample and first parts are the same
    BUILDER_CONFIGS.append(
        DiffusionDBConfig(
            name="all",
            part_ids=_PART_IDS,
            description="All images with their prompts and parameters",
        ),
    )

    # We also prove a text-only option, which loads the meatadata parquet file
    BUILDER_CONFIGS.append(
        DiffusionDBConfig(
            name="text_only",
            part_ids=[],
            description="Only include all prompts and parameters (no image)",
        ),
    )

    # Default to only load 1k random images
    DEFAULT_CONFIG_NAME = "random_1k"

    def _info(self):
        """Specify the information of DiffusionDB."""

        if self.config.name == "text_only":
            features = datasets.Features(
                {
                    "image_name": datasets.Value("string"),
                    "prompt": datasets.Value("string"),
                    "part_id": datasets.Value("int64"),
                    "seed": datasets.Value("int64"),
                    "step": datasets.Value("int64"),
                    "cfg": datasets.Value("float32"),
                    "sampler": datasets.Value("string"),
                },
            )

        else:
            features = datasets.Features(
                {
                    "image": datasets.Image(),
                    "prompt": datasets.Value("string"),
                    "seed": datasets.Value("int64"),
                    "step": datasets.Value("int64"),
                    "cfg": datasets.Value("float32"),
                    "sampler": datasets.Value("string"),
                },
            )

        return datasets.DatasetInfo(
            description=_DESCRIPTION,
            features=features,
            supervised_keys=None,
            homepage=_HOMEPAGE,
            license=_LICENSE,
            citation=_CITATION,
        )

    def _split_generators(self, dl_manager):
        # If several configurations are possible (listed in BUILDER_CONFIGS),
        # the configuration selected by the user is in self.config.name

        # dl_manager is a datasets.download.DownloadManager that can be used to
        # download and extract URLS It can accept any type or nested list/dict
        # and will give back the same structure with the url replaced with path
        # to local files. By default the archives will be extracted and a path
        # to a cached folder where they are extracted is returned instead of the
        # archive

        # Download and extract zip files of all sampled part_ids
        data_dirs = []
        json_paths = []

        for cur_part_id in self.config.part_ids:
            cur_url = _URLS[cur_part_id]
            data_dir = dl_manager.download_and_extract(cur_url)

            data_dirs.append(data_dir)
            json_paths.append(join(data_dir, f"part-{cur_part_id:06}.json"))

        # If we are in text_only mode, we only need to download the parquet file
        # For convenience, we save the parquet path in `data_dirs`
        if self.config.name == "text_only":
            data_dirs = [dl_manager.download(_URLS["metadata"])]

        return [
            datasets.SplitGenerator(
                name=datasets.Split.TRAIN,
                # These kwargs will be passed to _generate_examples
                gen_kwargs={
                    "data_dirs": data_dirs,
                    "json_paths": json_paths,
                },
            ),
        ]

    def _generate_examples(self, data_dirs, json_paths):
        # This method handles input defined in _split_generators to yield
        # (key, example) tuples from the dataset.
        # The `key` is for legacy reasons (tfds) and is not important in itself,
        # but must be unique for each example.

        # Load the metadata parquet file if the config is text_only
        if self.config.name == "text_only":
            metadata_df = pd.read_parquet(data_dirs[0])
            for _, row in metadata_df.iterrows():
                yield row["image_name"], {
                    "image_name": row["image_name"],
                    "prompt": row["prompt"],
                    "part_id": row["part_id"],
                    "seed": row["seed"],
                    "step": row["step"],
                    "cfg": row["cfg"],
                    "sampler": _SAMPLER_DICT[int(row["sampler"])],
                }

        else:
            # Iterate through all extracted zip folders for images
            num_data_dirs = len(data_dirs)
            assert num_data_dirs == len(json_paths)

            for k in range(num_data_dirs):
                cur_data_dir = data_dirs[k]
                cur_json_path = json_paths[k]

                json_data = load(open(cur_json_path, "r", encoding="utf8"))

                for img_name in json_data:
                    img_params = json_data[img_name]
                    img_path = join(cur_data_dir, img_name)

                    # Yields examples as (key, example) tuples
                    yield img_name, {
                        "image": {
                            "path": img_path,
                            "bytes": open(img_path, "rb").read(),
                        },
                        "prompt": img_params["p"],
                        "seed": int(img_params["se"]),
                        "step": int(img_params["st"]),
                        "cfg": float(img_params["c"]),
                        "sampler": img_params["sa"],
                    }
