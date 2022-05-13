#!/usr/bin/env python3

from argparse import ArgumentParser
import json
from os import scandir, environ
import os
from pathlib import Path
from pprint import pprint
import shutil
from typing import Dict, List, NamedTuple
from subprocess import call

import yaml


class Args(NamedTuple):
    cci_dir: Path
    conan_cache_dir: Path
    source_dir: Path
    install_dir: Path
    conan: str


def parse_args() -> Args:
    p = ArgumentParser()
    p.add_argument('--cci-dir', type=Path, required=True)
    p.add_argument('--conan-cache-dir', type=Path, required=True)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--install-dir', type=Path, required=True)
    p.add_argument('--conan', default='conan')
    return Args(**p.parse_args().__dict__)


def main(args: Args) -> None:
    if args.conan_cache_dir:
        environ['CONAN_USER_HOME'] = str(args.conan_cache_dir.absolute())

    failed = []

    cci = args.cci_dir / 'recipes'
    print(f'Parsing {cci.absolute()}')
    for recipe in scandir(cci):
        # for tests
        # if recipe.name != 'xz_utils':
        #     continue
        conf = Path(recipe) / 'config.yml'
        if conf.is_file():
            versions = read_versions(conf)
            for v, p in versions.items():
                conan_create(args.conan, recipe.name, v, p, args.source_dir, args.install_dir)
        else:
            print(f'{recipe} -- configless')
            for version in scandir(recipe):
                conanfile = Path(recipe) / version / 'conanfile.py'
                assert conanfile.is_file()

def read_versions(config: Path) -> Dict[str, Path]:
    result = dict()
    with open(config) as f:
        y = yaml.load(f, yaml.CLoader)
        for v, x in y['versions'].items():
            result[v] = config.parent / x['folder']
    return result


def conan_create(conan: str, package: str, version: str, path: Path, source_folder: Path, install_folder: Path) -> None:
    if install_folder.is_dir():
        shutil.rmtree(install_folder)
    os.makedirs(install_folder)
    if source_folder.is_dir():
        shutil.rmtree(source_folder)
    os.makedirs(source_folder)

    write_lock(package, version, install_folder)
    write_graph(package, version, install_folder)

    workdir = str(path.absolute())

    command = [conan, 'source', workdir, '-if', str(install_folder.absolute()), '-sf', str(source_folder.absolute())]
    print(f' -- {command}')
    return call(command) == 0


def write_graph(name: str, version: str, install_folder: Path) -> None:
    graph = {
 "options": [],
 "root": {
  "name": name,
  "version": version,
  "user": "avail",
  "channel": "script"
 }
}
    with open(install_folder / 'graph_info.json', 'w') as f:
        json.dump(graph, f, indent=1)

def write_lock(name: str, version: str, install_folder: Path) -> None:
    lock = {
 "graph_lock": {
  "nodes": {
   "0": {
    "ref": f'{name}/{version}@avail/script',
   }
  },
 },
 "profile_host": "[settings]\narch=x86_64\narch_build=x86_64\nbuild_type=Release\ncompiler=gcc\ncompiler.libcxx=libstdc++\ncompiler.version=11\nos=Linux\nos_build=Linux\n[options]\n[build_requires]\n[env]\n"
}
    with open(install_folder / 'conan.lock', 'w') as f:
        json.dump(lock, f, indent=1)

if __name__ == '__main__':
    main(parse_args())
