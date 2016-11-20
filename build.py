import argparse
import distutils
from distutils.command.build_ext import build_ext, CompileError
from distutils.core import Distribution
from glob import glob
import os.path
import shutil
from importlib import import_module
import os
import sys


class BuildSystem:
    def __init__(self, args):
        self.args = args

    def get_extension_by_path(self, path):
        module_import = os.path.splitext(path)[0].replace('/', '.')
        module = import_module(module_import)
        module.system = self
        extension = module.get_extension()

        base_path = os.path.dirname(path)

        def fix_path(p):
            if os.path.isabs(p):
                return p

            return os.path.abspath(os.path.join(base_path, p))

        for attr in ['sources', 'include_dirs', 'library_dirs', 'runtime_library_dirs']:
            val = getattr(extension, attr)
            if not val:
                continue

            val = [fix_path(v) for v in val]
            if attr == 'runtime_library_dirs':
                setattr(extension, attr, None)
                attr = 'extra_link_args'
                val = ['-Wl,-rpath,' + v for v in val]
                val = (getattr(extension, attr) or []) + val
            setattr(extension, attr, val)

        return extension

    def discover_extensions(self):
        self.extensions = []

        ext_files = glob('**/*_ext.py', recursive=True)
        self.extensions = [self.get_extension_by_path(f) for f in ext_files]

        return self.extensions


def dest_folder(mod_name):
    return '/'.join(mod_name.split('.')[:-1])


def prune():
    paths = glob('build/**/*.o', recursive=True)
    paths.extend(glob('build/**/*.so', recursive=True))
    for path in paths:
        os.remove(path)


def main():
    argparser = argparse.ArgumentParser('build')
    argparser.add_argument(
        '-d', dest='debug', const=True, action='store_const', default=False)
    argparser.add_argument(
        '--profile-generate', dest='profile_generate', const=True,
        action='store_const', default=False)
    argparser.add_argument(
        '--profile-use', dest='profile_use', const=True,
        action='store_const', default=False)
    argparser.add_argument(
        '--disable-reaper', dest='enable_reaper', const=False,
        action='store_const', default=True)
    argparser.add_argument('--path', dest='path')
    args = argparser.parse_args(sys.argv[1:])

    distutils.log.set_verbosity(1)

    system = BuildSystem(args)

    if args.path:
        ext_modules = [system.get_extension_by_path(args.path)]
    else:
        ext_modules = system.discover_extensions()
    dist = Distribution(dict(ext_modules=ext_modules))

    if args.debug:
        for ext_module in ext_modules:
            ext_module.extra_compile_args.extend(['-g', '-O0'])
    if args.profile_generate:
        for ext_module in ext_modules:
            ext_module.extra_compile_args.append('--profile-generate')
            ext_module.extra_link_args.append('-lgcov')
    if args.profile_use:
        for ext_module in ext_modules:
            if ext_module.name == 'parser.cparser':
                continue
            ext_module.extra_compile_args.append('--profile-use')

    if not args.debug:
        for ext_module in ext_modules:
            extra_compile_args = ext_module.extra_compile_args or []
            extra_compile_args.append('-flto')
            ext_module.extra_compile_args = extra_compile_args
            extra_link_args = ext_module.extra_link_args or []
            extra_link_args.append('-flto')
            ext_module.extra_link_args = extra_link_args

    prune()

    cmd = build_ext(dist)
    cmd.finalize_options()

    try:
        cmd.run()
    except CompileError:
        sys.exit(1)

    for ext_module in ext_modules:
        shutil.copy(
            cmd.get_ext_fullpath(ext_module.name),
            dest_folder(ext_module.name))


if __name__ == '__main__':
    main()
