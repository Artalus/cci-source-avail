#!/usr/bin/env python3

from argparse import ArgumentParser
import json
from os import scandir, environ
import os
from pathlib import Path
import shutil
import sys
from time import time
from typing import Dict, NamedTuple, Tuple
from subprocess import call

import yaml
from pathos.multiprocessing import ProcessingPool as Pool
from multiprocessing import current_process


class Args(NamedTuple):
    cci_dir: Path
    conan_cache_dir: Path
    source_dir: Path
    install_dir: Path
    conan: str
    pool: int


def parse_args() -> Args:
    p = ArgumentParser()
    p.add_argument('--cci-dir', type=Path, required=True)
    p.add_argument('--conan-cache-dir', type=Path, required=True)
    p.add_argument('--source-dir', type=Path, required=True)
    p.add_argument('--install-dir', type=Path, required=True)
    p.add_argument('--conan', default='conan')
    p.add_argument('--pool', type=int, default=4)
    return Args(**p.parse_args().__dict__)


def main(args: Args) -> None:
    recipes = 0
    configless = 0

    cci = args.cci_dir / 'recipes'
    print(f'Parsing {cci.absolute()}')

    profile_str = read_profile(args.conan)

    start = time()
    configurations = []
    for recipe in scandir(cci):
        # for tests
        # if recipes > 15:
        #     break
        # if recipe.name not in ['xz_utils', 'zyre', 'msys2', 'zlib']:
        #     continue
        recipes += 1
        conf = Path(recipe) / 'config.yml'
        if conf.is_file():
            versions = read_versions(conf)
            for v, p in versions.items():
                configurations.append((recipe.name, v, p))
        else:
            configless += 1
            print(f' -- {recipe.name} is configless')
            for version in scandir(recipe):
                conanfile = Path(recipe) / version / 'conanfile.py'
                assert conanfile.is_file()
                configurations.append((recipe.name, version.name, conanfile))
    pool = Pool(args.pool)
    def mapped_create(tpl: Tuple[str, str, Path]) -> bool:
        name, ver, pth = tpl
        return conan_create(args.conan, name, ver, pth, args.conan_cache_dir, args.source_dir, args.install_dir, profile_str)
    results = pool.map(mapped_create, configurations)
    success = len(list(x for x in results if x))
    failure = len(results) - success
    seconds_spent = int(time() - start)

    for i in range(5):
        print('='*80)
    print('   FINAL REPORT')
    print(f'TIME SPENT: {seconds_spent//3600}h {(seconds_spent//60)%60}m {seconds_spent%60}s')
    print(f'RECIPES TRAVERSED: {recipes}')
    print(f' of them configless: {configless}')
    print(f'PACKAGES CHECKED: {len(results)}')
    print(f' of them succeeded: {success}')
    print(f' and failed: {failure}')
    print('FAILED PACKAGES:')
    for tpl, result in zip(configurations, results):
        if not result:
            name, ver, pth = tpl
            print(f'{name}/{ver} - {pth}')
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


def conan_create(conan: str, package: str, version: str, path: Path, cache_folder: Path, source_folder: Path, install_folder: Path, profile: str) -> bool:
    real_if = install_folder / f'{package}-{version}'
    real_sf = source_folder / f'{package}-{version}'
    if real_if.is_dir():
        shutil.rmtree(real_if)
    os.makedirs(real_if)
    if real_sf.is_dir():
        shutil.rmtree(real_sf)
    os.makedirs(real_sf)

    write_lock(package, version, real_if, profile)
    write_graph(package, version, real_if)

    workdir = str(path.absolute())

    command = [conan, 'source', workdir, '-if', str(real_if.absolute()), '-sf', str(real_sf.absolute())]
    print(f' -- {command}')
    env_copy = environ.copy()
    env_copy['CONAN_USER_HOME'] = str((cache_folder / str(current_process().ident)).absolute())
    return call(command, env=env_copy) == 0


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
