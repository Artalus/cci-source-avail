#!/usr/bin/env python3

from argparse import ArgumentParser
import json
from os import scandir, environ
import os
from pathlib import Path
import shutil
import sys
from time import time
from typing import Dict, NamedTuple
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

    recipes = 0
    packages = 0
    configless = 0
    failed = []

    cci = args.cci_dir / 'recipes'
    print(f'Parsing {cci.absolute()}')

    profile_str = read_profile(args.conan)

    start = time()
    for recipe in scandir(cci):
        # for tests
        # if recipe.name not in ['xz_utils', 'zyre', 'msys2', 'zlib']:
        #     continue
        recipes += 1
        conf = Path(recipe) / 'config.yml'
        if conf.is_file():
            versions = read_versions(conf)
            for v, p in versions.items():
                succ = conan_create(args.conan, recipe.name, v, p, args.source_dir, args.install_dir, profile_str)
                packages += 1
                if not succ:
                    failed.append (f'{recipe.name}/{v} - {p}')
        else:
            configless += 1
            print(f' -- {recipe.name} is configless')
            for version in scandir(recipe):
                conanfile = Path(recipe) / version / 'conanfile.py'
                assert conanfile.is_file()
    seconds_spent = int(time() - start)

    for i in range(5):
        print('='*80)
    print('   FINAL REPORT')
    print(f'TIME SPENT: {seconds_spent//3600}h {(seconds_spent//60)%60}m {seconds_spent%60}s')
    print(f'RECIPES TRAVERSED: {recipes}')
    print(f' of them configless: {configless}')
    print(f'PACKAGES CHECKED: {packages}')
    print(f' of them succeeded: {packages-len(failed)}')
    print(f' and failed: {len(failed)}')
    print('FAILED PACKAGES:')
    for f in failed:
        print(f)
    for i in range(5):
        print('='*80)


def read_versions(config: Path) -> Dict[str, Path]:
    result = dict()
    with open(config) as f:
        y = yaml.load(f, yaml.Loader)
        for v, x in y['versions'].items():
            result[v] = config.parent / x['folder']
    return result

def read_profile(conan: str) -> str:
    # TODO: could use `conan profile show default`, but on windows its string results in
    #       'settings.compiler.runtime' value not defined
    if sys.platform == 'win32':
        return '[settings]\narch=x86_64\narch_build=x86_64\nbuild_type=Release\ncompiler=Visual Studio\ncompiler.runtime=MD\ncompiler.version=17\nos=Windows\nos_build=Windows\n[options]\n[build_requires]\n[env]\n'
    elif 'linux' in sys.platform:
        return '[settings]\narch=x86_64\narch_build=x86_64\nbuild_type=Release\ncompiler=gcc\ncompiler.libcxx=libstdc++\ncompiler.version=11\nos=Linux\nos_build=Linux\n[options]\n[build_requires]\n[env]\n'
    else:
        raise RuntimeError(f'Unsupported platform: {sys.platform}')


def conan_create(conan: str, package: str, version: str, path: Path, source_folder: Path, install_folder: Path, profile: str) -> bool:
    if install_folder.is_dir():
        shutil.rmtree(install_folder)
    os.makedirs(install_folder)
    if source_folder.is_dir():
        shutil.rmtree(source_folder)
    os.makedirs(source_folder)

    write_lock(package, version, install_folder, profile)
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

def write_lock(name: str, version: str, install_folder: Path, profile: str) -> None:
    lock = {
 "graph_lock": {
  "nodes": {
   "0": {
    "ref": f'{name}/{version}@avail/script',
   }
  },
 },
 "profile_host": profile.strip()
}
    with open(install_folder / 'conan.lock', 'w') as f:
        json.dump(lock, f, indent=1)

if __name__ == '__main__':
    main(parse_args())
